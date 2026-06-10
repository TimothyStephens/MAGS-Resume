import streamlit as st
import tempfile
import os
import json
import threading
from st_diff_viewer import diff_viewer
from pathlib import Path
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from langchain_core.callbacks import BaseCallbackHandler
from streamlit.runtime.scriptrunner import add_script_run_ctx, get_script_run_ctx

# Import from our backend
from mags_resume.utils.doc_ops import extract_text_from_docx, save_text_to_docx
from mags_resume.utils.config_parser import get_llm, register_callback_factory, clear_callback_factories
from mags_resume.graph import build_career_graph
from mags_resume.utils.db import init_db

st.set_page_config(layout="wide", page_title="MAGS-CareerDev Studio")
init_db()
st.title("MAGS-CareerDev: Resume Studio")

# --- Token Validation ---
expected_token = os.environ.get("MAGS_STREAMLIT_TOKEN")
query_token = st.query_params.get("token")

if expected_token: # Only enforce if a token was set by the CLI
    if not query_token or query_token != expected_token:
        st.error("Unauthorized Access: Please use the full URL with the correct token provided by the CLI.")
        st.stop()
    else:
        # Clear the token from query params to keep the URL clean after validation
        # This also prevents the token from being accidentally shared if the user copies the URL
        st.query_params.pop("token", None)


# --- Application Manager Sidebar ---
with st.sidebar:
    st.header("📂 Application Workspace")

    # If an application is active, show its details and a reset button
    if 'app_name' in st.session_state:
        st.success(f"Active: {st.session_state['app_name']}")
        app_dir = Path(st.session_state['app_dir'])

        # List files
        st.markdown("### Files")
        files = list(app_dir.glob("*"))
        if files:
            for f in files:
                st.caption(f"📄 {f.name}")
        else:
            st.caption("No files yet.")

        if st.button("✨ Start New Application"):
            keys_to_clear = ['app_dir', 'app_name', 'original', 'draft', 'qa_chat_history', 'ai_job_ad']
            for key in keys_to_clear:
                if key in st.session_state:
                    del st.session_state[key]
            st.rerun()

    # Otherwise, show the input to create a new workspace
    else:
        st.info("Start here: Enter an application name to organize your files.")
        app_name_input = st.text_input("Application Name", placeholder="e.g. Google_SrEngineer", help="Creates a folder to store your resume and Q&A.")
        if app_name_input:
            safe_name = "".join([c if c.isalnum() or c in ('-','_') else '_' for c in app_name_input])
            app_dir = Path("applications") / safe_name
            if st.button(f"Set Workspace: {safe_name}"):
                app_dir.mkdir(parents=True, exist_ok=True)
                st.session_state['app_dir'] = str(app_dir)
                st.session_state['app_name'] = safe_name
                st.rerun()

    st.divider()
    st.header("👤 Master Profile")
    st.caption("Upload a resume to set it as your default.")
    
    uploaded_master = st.file_uploader("Update Master Resume", type=["docx", "md", "txt"], key="master_upload")
    if uploaded_master:
        # Determine path
        ext = Path(uploaded_master.name).suffix
        save_path = Path(f"master_resume{ext}")
        with open(save_path, "wb") as f:
            f.write(uploaded_master.getbuffer())
        st.success(f"Saved {save_path.name}!")
        st.rerun()

    # Detect existing master file
    master_file = next((p for p in Path(".").glob("master_resume.*") if p.suffix in [".docx", ".md", ".txt"]), None)
    if master_file:
        st.success(f"✅ Master Found: {master_file.name}")

    st.divider()
    st.header("⚙️ Preferences")
    
    # Persistence logic for preferences
    prefs_path = Path(".MAGS-Resume/ui_preferences.json")
    
    def save_prefs():
        current = {}
        if prefs_path.exists():
            try: current = json.loads(prefs_path.read_text(encoding="utf-8"))
            except: pass
        
        # Save known preferences if they exist in session state
        if "static_filename" in st.session_state:
            current["static_filename"] = st.session_state.static_filename
        if "max_iterations" in st.session_state:
            current["max_iterations"] = st.session_state.max_iterations
            
        prefs_path.parent.mkdir(exist_ok=True)
        prefs_path.write_text(json.dumps(current), encoding="utf-8")

    # Load defaults
    default_val = "My_Resume.docx"
    default_iters = 2
    if prefs_path.exists():
        try: 
            data = json.loads(prefs_path.read_text(encoding="utf-8"))
            default_val = data.get("static_filename", default_val)
            default_iters = data.get("max_iterations", default_iters)
        except: pass

    st.text_input("Static Output Filename", value=default_val, key="static_filename", on_change=save_prefs, help="Default filename for exported resumes. Since folders organize applications, you can keep this static.")
    st.number_input("Max AI Revisions", min_value=0, max_value=5, value=default_iters, key="max_iterations", on_change=save_prefs, help="0 = First draft only. 1+ = Refine based on reviewer feedback.")

# Create tabs for different workflows
tab_ai, tab_qa = st.tabs(["Resume Assistant", "Application Q&A"])

# --- AI Resume Assistant Workflow ---
with tab_ai:
    st.header("Generate AI-Tailored Resume Draft")
    st.markdown("Use AI to tailor your existing resume for a specific job description.")
    col1, col2 = st.columns(2)
    with col1:
        resume_file = st.file_uploader("1. Upload Original Resume", type=["docx", "md", "txt"], key="ai_resume_upload")
        if not resume_file and master_file:
            st.info(f"Using Default: {master_file.name}")
    with col2:
        with st.form("ai_draft_form"):
            job_ad = st.text_area("2. Paste Job Description Here", height=150, key="ai_job_ad")
            submitted = st.form_submit_button("3. Generate AI Draft", type="primary")

    # Determine readiness
    is_ready = (resume_file or master_file) and job_ad
    if submitted and not is_ready:
        st.warning("Please upload a resume and paste a job description to proceed.")

    class StatusCallbackHandler(BaseCallbackHandler):
        def __init__(self, status_container, role, model_name, lock=None):
            self.status = status_container
            self.role = role or "Agent"
            self.model_name = model_name
            self.ctx = get_script_run_ctx()
            self.lock = lock or threading.Lock()
        
        def on_llm_start(self, serialized, prompts, **kwargs):
            if self.ctx:
                add_script_run_ctx(ctx=self.ctx)
                
            msg = f"**{self.role.replace('_', ' ').title()}** is thinking..."
            
            with self.lock:
                self.status.write(msg)
                self.status.update(label=msg, state="running")

    if submitted and is_ready:
        # Auto-save Job Ad if workspace is active
        if 'app_dir' in st.session_state:
            ad_path = Path(st.session_state['app_dir']) / "job_description.txt"
            ad_path.write_text(job_ad, encoding="utf-8")
            st.toast(f"Saved Job Description to {ad_path.name}")

        with st.status("Initializing AI Agents...", expanded=True) as status:
            # Determine source
            if resume_file:
                file_payload = resume_file
                file_name = resume_file.name
            else:
                file_payload = master_file
                file_name = master_file.name

            tmp_path = None
            
            # If it's a Streamlit UploadedFile
            if hasattr(file_payload, "getvalue"):
                    if file_name.lower().endswith(".docx"):
                        with tempfile.NamedTemporaryFile(delete=False, suffix=".docx") as tmp:
                            tmp.write(file_payload.getvalue())
                            tmp_path = tmp.name
                        original_text = extract_text_from_docx(tmp_path)
                    else:
                        original_text = file_payload.getvalue().decode("utf-8")
            
            # If it's a pathlib Path (Master file from disk)
            elif isinstance(file_payload, Path):
                if file_payload.suffix == ".docx":
                    original_text = extract_text_from_docx(str(file_payload))
                else:
                    original_text = file_payload.read_text(encoding="utf-8")
            
            graph = build_career_graph()
            initial_state = {
                "job_ad_text": job_ad,
                "original_content": original_text,
                "current_draft": "",
                "review_comments": [],
                "iteration_count": 0,
                "max_iterations": st.session_state.get("max_iterations", 2),
                "task_type": "resume",
                "config_path": "config.yaml"
            }

            # Shared lock for UI updates in this run to prevent concurrency crashes
            ui_lock = threading.Lock()

            # Register UI callback for status updates
            def status_factory(role, model_name):
                return StatusCallbackHandler(status, role, model_name, lock=ui_lock)
            
            register_callback_factory(status_factory)
            try:
                final_state = graph.invoke(initial_state)
                status.update(label="Workflow Complete!", state="complete", expanded=False)
                
                st.session_state['original'] = original_text
                st.session_state['draft'] = final_state['current_draft']
                st.session_state['editor'] = final_state['current_draft']
            finally:
                if tmp_path: os.remove(tmp_path)
                clear_callback_factories()

            st.success("AI draft generated! Scroll down to review and edit.")
            
            # AUTO-SAVE: Initial Draft
            if 'app_dir' in st.session_state:
                # Determine filename for autosave
                if st.session_state.get("static_filename"):
                    as_name = st.session_state["static_filename"]
                else:
                    # Logic duplication for safe default
                    as_base = "Resume"
                    if hasattr(file_payload, "name"):
                        as_base = Path(file_payload.name).stem
                    elif isinstance(file_payload, Path):
                        as_base = file_payload.stem
                    
                    if 'app_name' in st.session_state:
                        as_name = f"{as_base}_{st.session_state['app_name']}.docx"
                    else:
                        as_name = f"{as_base}_Optimized.docx"
                
                if not as_name.endswith('.docx'):
                    as_name += '.docx'
                
                as_path = Path(st.session_state['app_dir']) / as_name
                try:
                    save_text_to_docx(final_state['current_draft'], str(as_path))
                    st.toast(f"✅ Auto-saved draft to {as_name}")
                except Exception as e:
                    st.error(f"Auto-save failed: {e}")


    # ==========================================
    # LIVE EDIT, DIFF, & EXPORT
    # ==========================================
    if 'draft' in st.session_state:
        st.divider()
        st.header("Review, Refine & Export")
        
        st.subheader("1. Edit Your Document")
        edited_draft = st.text_area(
            "Make your manual adjustments below. The diff viewer will update instantly.", 
            value=st.session_state['draft'], 
            height=400,
            key="editor"
        )
        
        st.subheader("2. Live Diff Preview")
        diff_viewer(st.session_state['original'], edited_draft, lang='markdown', split_view=True)
        
        st.subheader("3. Export Final Document")
        
        # Use static preference if available, otherwise dynamic
        if st.session_state.get("static_filename"):
            default_name = st.session_state["static_filename"]
        else:
            # Create a more descriptive default file name
            base_name = "Resume"
            # Check if a file was uploaded and get its name without extension
            if 'ai_resume_upload' in st.session_state and st.session_state.ai_resume_upload:
                base_name = Path(st.session_state.ai_resume_upload.name).stem
            elif master_file:
                base_name = master_file.stem

            if 'app_name' in st.session_state:
                # e.g., "Timothy_Stephens_Resume_Google_SrEngineer.docx"
                default_name = f"{base_name}_{st.session_state['app_name']}.docx"
            else:
                # e.g., "Timothy_Stephens_Resume_Optimized.docx"
                default_name = f"{base_name}_Optimized.docx"

        file_name = st.text_input("Set output file name:", default_name, key="export_filename")
        
        # AUTO-SAVE: On Editor Change
        if 'app_dir' in st.session_state and edited_draft:
            # Ensure extension
            safe_file_name = file_name if file_name.endswith('.docx') else f"{file_name}.docx"
            auto_save_path = Path(st.session_state['app_dir']) / safe_file_name
            
            # Save quietly to avoid full page reload interruption, or use toast
            save_text_to_docx(edited_draft, str(auto_save_path))
            # We use a unique key for the toast to avoid spamming if desired, or just show it.
            # st.toast(f"Saved: {safe_file_name}") 

        if st.button("Approve & Save to .docx", type="primary", key="save_docx"):
            if not file_name.endswith('.docx'):
                file_name += '.docx'
            
            save_path = file_name
            if 'app_dir' in st.session_state:
                save_path = str(Path(st.session_state['app_dir']) / file_name)

            save_text_to_docx(edited_draft, save_path)
            st.success(f"🎉 Successfully saved to '{save_path}'!")
            st.balloons()

# --- Application Q&A Workflow ---
with tab_qa:
    st.header("Job Application Question Assistant")
    st.info("Use this chat to answer screening questions based on your Resume and the Job Description.")

    # 1. Gather Context
    # Job Ad is in st.session_state['ai_job_ad'] (from text_area key in Tab 1)
    job_ad_text = st.session_state.get("ai_job_ad", "")
    
    # Resume text might be in 'original' if generated, or we check the upload widget
    resume_text = st.session_state.get("original", "")
    
    if not resume_text:
        # Try to read from upload widget if user hasn't generated a draft yet
        uploaded_file = st.session_state.get("ai_resume_upload")
        if uploaded_file:
            try:
                if uploaded_file.name.lower().endswith(".docx"):
                    with tempfile.NamedTemporaryFile(delete=False, suffix=".docx") as tmp:
                        tmp.write(uploaded_file.getvalue())
                        tmp_path = tmp.name
                    resume_text = extract_text_from_docx(tmp_path)
                    os.remove(tmp_path)
                else:
                    resume_text = uploaded_file.getvalue().decode("utf-8")
                # Store for session
                st.session_state["original"] = resume_text
            except Exception as e:
                st.error(f"Error reading resume file: {e}")
        elif master_file:
            # Fallback to master
            try:
                if master_file.suffix == ".docx":
                    resume_text = extract_text_from_docx(str(master_file))
                else:
                    resume_text = master_file.read_text(encoding="utf-8")
                st.session_state["original"] = resume_text
            except Exception as e:
                st.error(f"Error reading master file: {e}")

    # 2. Check Readiness
    if not job_ad_text or not resume_text:
        st.warning("⚠️ Please provide a **Resume** and **Job Description** in the 'AI Resume Assistant' tab to initialize the context.")
    else:
        # 4. Save History (Moved to top for better layout)
        if st.session_state.get("qa_chat_history") and 'app_dir' in st.session_state:
            col_head, col_btn = st.columns([4, 1])
            with col_btn:
                if st.button("💾 Save Q&A", key="save_qa_top"):
                    qa_path = Path(st.session_state['app_dir']) / "qa_summary.txt"
                    with open(qa_path, "w", encoding="utf-8") as f:
                        f.write(f"Application Q&A Summary\n")
                        f.write(f"Application: {st.session_state.get('app_name', 'Unknown')}\n\n")
                        for msg in st.session_state["qa_chat_history"]:
                            role = msg["role"].upper()
                            f.write(f"[{role}]\n{msg['content']}\n\n{'-'*20}\n\n")
                    st.toast(f"Saved Q&A summary to {qa_path}")
            st.divider()

        # 3. Chat Interface
        if "qa_chat_history" not in st.session_state:
            st.session_state["qa_chat_history"] = []

        # Create a container for the chat history to enforce rendering order
        chat_container = st.container()
        with chat_container:
            for msg in st.session_state["qa_chat_history"]:
                with st.chat_message(msg["role"]):
                    st.markdown(msg["content"])

        # Input
        if question := st.chat_input("Paste an application question here..."):
            # User Message
            st.session_state["qa_chat_history"].append({"role": "user", "content": question})
            with chat_container.chat_message("user"):
                st.markdown(question)

            # Assistant Response
            with chat_container.chat_message("assistant"):
                with st.spinner("Drafting answer..."):
                    llm = get_llm(role="chat")
                    
                    system_prompt = (
                        "You are a helpful career assistant aiding a candidate with a job application.\n"
                        "Formulate a professional, tailored answer to the user's question based on the provided Resume and Job Description.\n"
                        "Highlight relevant skills and experience truthfully.\n\n"
                        f"### JOB DESCRIPTION\n{job_ad_text}\n\n"
                        f"### CANDIDATE RESUME\n{resume_text}\n"
                    )
                    
                    messages = [SystemMessage(content=system_prompt)]
                    for m in st.session_state["qa_chat_history"]:
                        if m["role"] == "user":
                            messages.append(HumanMessage(content=m["content"]))
                        else:
                            messages.append(AIMessage(content=m["content"]))
                    
                    response = llm.invoke(messages)
                    
                    # Handle potential list content from Anthropic/Multimodal models
                    content = response.content
                    if isinstance(content, list):
                        content = "".join([
                            block.get("text", "") 
                            for block in content 
                            if isinstance(block, dict) and block.get("type") == "text"
                        ])
                    
                    st.markdown(content)
                    st.session_state["qa_chat_history"].append({"role": "assistant", "content": content})
                    
                    # AUTO-SAVE: Q&A History
                    if 'app_dir' in st.session_state:
                        qa_path = Path(st.session_state['app_dir']) / "qa_summary.txt"
                        try:
                            with open(qa_path, "w", encoding="utf-8") as f:
                                f.write(f"Application Q&A Summary\n")
                                f.write(f"Application: {st.session_state.get('app_name', 'Unknown')}\n\n")
                                for msg in st.session_state["qa_chat_history"]:
                                    role_label = msg["role"].upper()
                                    f.write(f"[{role_label}]\n{msg['content']}\n\n{'-'*20}\n\n")
                            st.toast("✅ Q&A Response Auto-saved")
                        except Exception as e:
                            st.error(f"Auto-save failed: {e}")
        st.rerun()