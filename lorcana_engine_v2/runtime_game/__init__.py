__all__ = [
    "board_setup",
    "lorcana_player_view",
    "lorcana_runtime_config",
    "lorcana_runtime_zones",
    "setup_lorcana_g",
]


def __getattr__(name):
    if name in __all__:
        from . import definition

        return getattr(definition, name)
    raise AttributeError(name)
