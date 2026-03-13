from langchain_core.prompts import ChatPromptTemplate
from mags_resume.state import CareerState
from mags_resume.utils.config_parser import get_llm
from mags_resume.utils.logger import logger
from mags_resume.utils.prompt_loader import load_prompt

def writer_node(state: CareerState) -> dict:
    logger.info(f"Writer node starting. Iteration: {state['iteration_count']}")
    llm = get_llm(role="writer", config_path=state["config_path"])
    model_name = getattr(llm, "model_name", getattr(llm, "model", "unknown_model"))
    logger.info(f"Writer Agent using model: {model_name}")
    
    if state["iteration_count"] == 0:
        logger.info("Generating first draft from original resume and job ad.")
        logger.debug(f"Input stats - Job Ad: {len(state['job_ad_text'])} chars, Original Resume: {len(state['original_content'])} chars.")
        system_prompt = load_prompt("writer_initial_system.md")
        human_prompt = load_prompt("writer_initial_human.md")
        params = {"job_ad": state["job_ad_text"], "original": state["original_content"]}
    else:
        logger.info("Revising draft based on feedback.")
        feedback_count = len(state.get("review_comments", []))
        logger.info(f"Incorporating {feedback_count} feedback items.")
        system_prompt = load_prompt("writer_revise_system.md")
        human_prompt = load_prompt("writer_revise_human.md")
        params = {"draft": state["current_draft"], "feedback": "\n".join(state["review_comments"])}

    prompt = ChatPromptTemplate.from_messages([("system", system_prompt), ("human", human_prompt)])
    logger.debug(f"Writer Prompt Params: {params}")
    chain = prompt | llm
    
    logger.info("Invoking Writer LLM...")
    response = chain.invoke(params)
    logger.info("Writer LLM generation complete.")
    logger.debug(f"Writer Response Content: {response.content}")
    
    if isinstance(response.content, list):
        draft_content = "".join([
            block.get("text", "") 
            for block in response.content 
            if isinstance(block, dict) and block.get("type") == "text"
        ])
    else:
        draft_content = str(response.content)
        
    logger.info(f"Generated draft length: {len(draft_content)} chars.")
    
    return {
        "current_draft": draft_content,
        "iteration_count": state["iteration_count"] + 1,
        "review_comments": [] # Clear old comments
    }