from pathlib import Path

_CACHE = {}

def pick_prompt(intent: str, override_mode: str = None) -> str:
    swing = {"morning_analysis", "screener_verify", "analyze_symbol",
             "position_update", "position_advice", "swing_analysis"}

    if override_mode in ["swing", "general"]:
        file_name = f"{override_mode}.md"
    else:
        file_name = "swing.md" if intent in swing else "general.md"

    if file_name not in _CACHE:
        try:
            _CACHE[file_name] = Path(__file__).parent.joinpath(file_name).read_text(encoding="utf-8")
        except FileNotFoundError:
            _CACHE[file_name] = Path(__file__).parent.joinpath("swing.md").read_text(encoding="utf-8")
    return _CACHE[file_name]
