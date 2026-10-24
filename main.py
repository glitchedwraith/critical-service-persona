from pydantic_core.core_schema import model_field
from strands import Agent
from strands.models import BedrockModel
import boto3

# define model to use
model = BedrockModel(
    model_id="claude-opus-4.5",
    region_name="us-east-1",
)

SYSTEM_PROMPT = """
You are taking on the persona of Dana Reyes, a Emergency Operations Center (EOC) public-information officer.
Text residents official bulletins.
When responding to residents, only respond with validated official data.
Search for emerging rumors, verify them with Bedrock, and draft a clarification for a human to review and approve.
After sending clarifications, track whether the rumor is dying down or not.
"""

agent = Agent(model=model)

agent("wazzup")



