from constants import SCREEN_WIDTH, SCREEN_HEIGHT

def get_gui_agent(gui_agent_name, remote_client):
    if "gpt" in gui_agent_name and "/omniparser" in gui_agent_name:
        from agent.openai_omniparser import OpenAI_OmniParser_Agent, GPT_OMNIPARSER_SYSTEM_PROMPT
        return OpenAI_OmniParser_Agent(
            model = gui_agent_name.split('/')[0],
            system_prompt = GPT_OMNIPARSER_SYSTEM_PROMPT,
            remote_client = remote_client,
            screenshot_rolling_window = 3,
            top_p = 0.9,
            temperature = 1.0,
            device = 'cuda'
        )
    elif "openai/computer-use-preview" in gui_agent_name:
        from agent.openai_cua import OpenAI_CUA, CUA_SYSTEM_PROMPT
        return OpenAI_CUA(
            model = gui_agent_name.split('/')[1],
            system_prompt = CUA_SYSTEM_PROMPT,
            remote_client = remote_client,
            only_n_most_recent_images = 3,
            top_p = 0.9,
            temperature = 1.0
        )
    elif "gpt" in gui_agent_name:
        from agent.openai import OpenAI_General_Agent, GPT_SYSTEM_PROMPT
        return OpenAI_General_Agent(
            model = gui_agent_name, 
            system_prompt = GPT_SYSTEM_PROMPT,
            remote_client = remote_client,
            screenshot_rolling_window = 3,
            top_p = 0.9,
            temperature = 1.0
        )
    elif "claude-3-7-sonnet-20250219" in gui_agent_name and "computer-use-2025-01-24" in gui_agent_name:
        from agent.anthropic import ClaudeComputerUseAgent, CLAUDE_CUA_SYSTEM_PROMPT
        return ClaudeComputerUseAgent(
            model = gui_agent_name.split('/')[0],
            betas = gui_agent_name.split('/')[1:],
            max_tokens = 8192,
            display_width = SCREEN_WIDTH,
            display_height = SCREEN_HEIGHT,
            only_n_most_recent_images = 3,
            system_prompt = CLAUDE_CUA_SYSTEM_PROMPT,
            remote_client = remote_client
        )
    elif "UI-TARS-7B-DPO" in gui_agent_name:
        from agent.uitars import UITARS_GUI_AGENT, UITARS_COMPUTER_SYSTEM_PROMPT
        return UITARS_GUI_AGENT(
            model = "UI-TARS-7B-DPO",
            vllm_base_url = "http://127.0.0.1:8000/v1",
            system_prompt = UITARS_COMPUTER_SYSTEM_PROMPT,
            remote_client = remote_client,
            only_n_most_recent_images = 3,
            max_tokens = 12800,
            top_p = 0.9,
            temperature = 1.0
        )
    elif "showlab/ShowUI-2B" in gui_agent_name:
        from agent.showui import ShowUI_Agent, _NAV_SYSTEM, _NAV_FORMAT
        return ShowUI_Agent(
            model_name = "showlab/ShowUI-2B",
            system_prompt = _NAV_SYSTEM + _NAV_FORMAT,
            remote_client = remote_client,
            min_pixels = 256*28*28,
            max_pixels = 1344*28*28
        )
    elif "gemini" in gui_agent_name:
        from agent.gemini import Gemini_General_Agent, GEMINI_SAFETY_CONFIG, GEMINI_SYSTEM_PROMPT
        return Gemini_General_Agent(
            model = gui_agent_name,
            system_prompt = GEMINI_SYSTEM_PROMPT,
            remote_client = remote_client,
            only_n_most_recent_images = 3,
            max_tokens = 12800,
            top_p = 0.9,
            temperature = 1.0,
            safety_config = GEMINI_SAFETY_CONFIG
        )
    raise NotImplementedError(f'Agent "{gui_agent_name}" not implemented')