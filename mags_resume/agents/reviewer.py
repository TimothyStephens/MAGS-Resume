import asyncio
from langchain_core.prompts import ChatPromptTemplate
from mags_resume.state import CareerState
from mags_resume.utils.config_parser import get_reviewer_llms
from mags_resume.utils.logger import logger
from mags_resume.utils.prompt_loader import load_prompt

async def _get_review(llm, state: CareerState) -> str:
    model_name = getattr(llm, "model_name", getattr(llm, "model", "unknown_model"))
    logger.debug(f"Reviewer ({model_name}) starting review...")
    prompt = ChatPromptTemplate.from_messages([
        ("system", load_prompt("reviewer_system.md")),
        ("human", load_prompt("reviewer_human.md"))
    ])
    
    chain = prompt | llm
    params = {"job_ad": state["job_ad_text"], "draft": state["current_draft"]}
    logger.debug(f"Reviewer ({model_name}) Prompt Params: {params}")
    response = await chain.ainvoke(params)
    
    if isinstance(response.content, list):
        review_text = "".join([
            block.get("text", "") 
            for block in response.content 
            if isinstance(block, dict) and block.get("type") == "text"
        ])
    else:
        review_text = str(response.content)

    logger.debug(f"Reviewer ({model_name}) Response Content: {review_text}")
    logger.debug(f"Reviewer ({model_name}) finished. Response length: {len(review_text)} chars.")
    return review_text

async def _run_reviews(state: CareerState):
    llms = get_reviewer_llms(config_path=state["config_path"])
    logger.info(f"Dispatching reviews to {len(llms)} models.")
    tasks = [_get_review(llm, state) for llm in llms]
    return await asyncio.gather(*tasks)

def multi_llm_review_node(state: CareerState) -> dict:
    logger.info("Reviewer node starting.")
    reviews = asyncio.run(_run_reviews(state))
    logger.info(f"Received {len(reviews)} reviews from models.")
    actionable_comments = [rev for rev in reviews if "LGTM" not in rev.upper()]
    logger.info(f"Found {len(actionable_comments)} actionable comments.")
    return {"review_comments": actionable_comments}