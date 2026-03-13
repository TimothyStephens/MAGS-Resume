from typing import TypedDict, List

class CareerState(TypedDict):
    job_ad_text: str          
    original_content: str     
    current_draft: str        
    
    review_comments: List[str] 
    
    iteration_count: int      
    max_iterations: int       
    task_type: str            # 'resume' or 'questions'
    config_path: str