from langgraph.constants import END, START
from langgraph.graph import StateGraph
from mags_resume.state import CareerState
from mags_resume.agents.writer import writer_node
from mags_resume.agents.reviewer import multi_llm_review_node
from mags_resume.utils.logger import logger

def evaluate_reviews(state: CareerState) -> str:
    iteration = state.get("iteration_count", 0)
    logger.info(f"Evaluating review comments for iteration {iteration}.")
    if len(state.get("review_comments", [])) > 0:
        logger.info(f"Found {len(state['review_comments'])} comments. Sending for revision.")
        return "revise"
    logger.info("No actionable comments found. Approving draft.")
    return "approved"

def route_writer(state: CareerState) -> str:
    """Decides whether to send for review or end if max iterations reached."""
    if state["iteration_count"] > state["max_iterations"]:
        logger.info("Max iterations reached. Ending workflow without further review.")
        return "end"
    return "reviewers"

def build_career_graph():
    workflow = StateGraph(CareerState)
    
    workflow.add_node("writer", writer_node)
    workflow.add_node("reviewers", multi_llm_review_node)
    
    workflow.add_edge(START, "writer")
    
    # Check iteration limit immediately after writing to save tokens on unnecessary reviews
    workflow.add_conditional_edges(
        "writer",
        route_writer,
        {"reviewers": "reviewers", "end": END}
    )
    
    workflow.add_conditional_edges(
        "reviewers",
        evaluate_reviews,
        {
            "approved": END,
            "revise": "writer"
        }
    )
    
    return workflow.compile()