from pathlib import Path

FORBIDDEN = {
    "domain": ("features.", "adapters.", "core.database", "motor", "aiohttp", "aiogram"),
    "adapters": ("features.",),
}


def test_layer_boundaries():
    """Verify that domain and adapters obey the one-directional dependency rule."""
    base_dir = Path(__file__).resolve().parent.parent
    for layer, banned in FORBIDDEN.items():
        layer_dir = base_dir / layer
        if not layer_dir.exists():
            continue
        for path in layer_dir.rglob("*.py"):
            src = path.read_text(encoding="utf-8")
            for bad in banned:
                assert f"import {bad}" not in src and f"from {bad}" not in src, (
                    f"{path.relative_to(base_dir)} violates layering: imports {bad}"
                )
