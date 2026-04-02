# -*- coding: utf-8 -*-
"""碁華 Goka GO - エントリーポイント

全モジュールは igo/ パッケージに分割されています。
このファイルは後方互換性のため、全シンボルを再エクスポートします。
"""

# --- Initialize config, theme, language ---
from igo.config import (
    _get_app_data_dir, _get_install_dir, _init_config_if_needed,
    _get_db_path, get_offer_timeout_ms,
)
_init_config_if_needed()

from igo.theme import (
    THEMES, T, get_current_theme_name,
    _load_theme_from_config, _load_language_from_config, _save_language_to_config,
)
_load_theme_from_config()
_load_language_from_config()

# --- Re-export all symbols for backward compatibility ---
from igo.constants import (
    APP_NAME, APP_VERSION, APP_BUILD, UPDATE_CHECK_URL,
    BOARD_SIZE, CELL_SIZE, MARGIN, STONE_RADIUS, STAR_RADIUS,
    TIME_LIMIT, NET_TCP_PORT, NET_UDP_PORT, NET_BROADCAST_INTERVAL,
    EMPTY, BLACK, WHITE, STAR_POINTS, GO_RANKS,
    HAS_CLOUD, CLOUD_SERVER_URL, API_BASE_URL,
)
from igo.elo import (
    ELO_RANGES, ELO_RANGES_BY_LANG, ELO_K_FACTOR, ELO_MIN, ELO_MAX,
    get_elo_ranges, rank_to_initial_elo, _is_dan_rank,
    elo_to_rank, elo_to_display_rank, calculate_elo_update,
    rank_to_localized, get_localized_go_ranks, localized_rank_to_internal,
)
from igo.database import UserDatabase
from igo.rendering import (
    _make_stone_photoimage, _load_board_texture_original, _make_board_texture,
)
from igo.timer import ByoyomiTimer
from igo.network import _net_send, _net_recv, GameServer, NetworkGame
from igo.game_logic import (
    _neighbors, _get_group, _remove_group, _board_key, GoGame,
)
from igo.katago import (
    KataGoGTP, _moves_to_katago, _katago_score, _katago_winrate,
    calculate_territory_chinese,
)
from igo.ui_helpers import (
    _ime_halfwidth_alphanumeric, _entry_cfg, _configure_combo_style,
    _apply_combo_listbox_style, _disable_ime_for, _validate_ascii,
)
from igo.sgf import _parse_sgf_text, save_sgf, load_sgf
from igo.sound import _find_stone_sound, _play_stone_sound
from igo.promotion import PromotionPopup
from igo.login_screen import LoginScreen
from igo.register_screen import RegisterScreen
from igo.match_dialog import MatchDialog
from igo.match_offer_dialog import MatchOfferDialog
from igo.kifu_dialog import KifuDialog
from igo.go_board import GoBoard
from igo.app import App


def main():
    app = App()
    app.run()


if __name__ == "__main__":
    main()
