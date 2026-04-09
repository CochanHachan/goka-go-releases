# lang.py  -  UI string translations for 碁華 (Goka GO)
# Supported languages: ja (Japanese), en (English), zh (Simplified Chinese), ko (Korean)

STRINGS = {
    "ja": {
        # --- Login screen ---
        "login_title":      "碁華 ログイン",
        "login_handle":     "ハンドルネーム",
        "login_password":   "パスワード",
        "login_btn":        "ログイン",

        # --- Register screen ---
        "reg_title":        "新規アカウント作成",
        "reg_realname":     "氏名",
        "reg_handle":       "ハンドルネーム",
        "reg_password":     "パスワード（半角英数字記号４文字以上）",
        "reg_password2":    "パスワード確認",
        "reg_rank":         "棋力",
        "reg_btn":          "アカウント作成",
        "reg_back":         "戻る",
        "reg_handle_warn":  "ハンドルネームは20字以内です。",

        # --- Toolbar buttons ---
        "btn_game":         "対局",
        "btn_resign":       "投了",
        "btn_pass":         "パス",
        "btn_score":        "地合計算",
        "btn_kifu":         "棋譜",
        "btn_reset":        "初期化",
        "btn_logout":       "ログアウト",

        # --- Common buttons ---
        "btn_close":        "閉じる",
        "btn_accept":       "承諾",
        "btn_decline":      "辞退",
        "btn_reject":       "拒否",
        "btn_cancel":       "取消",
        "btn_apply":        "対局申込",
        "btn_host":         "対局申請",
        "btn_show":         "表示",

        # --- Menu: File ---
        "menu_file":        "ファイル(F)",
        "menu_new":         "新規(N)",
        "menu_open":        "開く(O)",
        "menu_save":        "上書き保存(S)",
        "menu_saveas":      "名前を付けて保存(A)",
        "menu_exit":        "終了(X)",

        # --- Menu: Settings ---
        "menu_settings":    "設定(G)",
        "menu_speed":       "再生スピード(S)",
        "menu_language":    "言語(L)",

        # --- Menu: View ---
        "menu_view":        "表示(V)",
        "menu_board":       "盤選択",

        # --- Menu: Game ---
        "menu_game":        "対局(P)",
        "menu_game_start":  "対局",
        "menu_resign":      "投了",
        "menu_pass":        "パス",
        "menu_score":       "地合計算",
        "menu_kifu":        "棋譜",
        "menu_review":      "検討",
        "menu_review_end":  "検討終了",

        # --- Menu: Help ---
        "menu_help":        "ヘルプ(H)",
        "menu_howto":       "遊び方(*)",
        "menu_features":    "機能(*)",
        "menu_about":       "バージョン情報(*)",

        # --- Window titles ---
        "title_match_dialog":   "対局申請",
        "title_offer_dialog":   "対局の申し込みです！",
        "title_kifu_dialog":    "棋譜一覧",
        "title_score":          "地合計算",
        "title_howto":          "遊び方",
        "title_features":       "機能",
        "title_about":          "バージョン情報",

        # --- MatchDialog labels ---
        "match_settings":       "対局条件設定",
        "match_time":           "持ち時間",
        "match_komi":           "コミ",
        "match_byoyomi":        "秒読み",
        "match_periods":        "回数",
        "match_hosting":        "対局申請中です。",
        "match_no_opponent":    "対局承諾者が不在です。対局条件を変えて申請してみてください。",
        "match_cancelled":      "申し込みを取り消しました",
        "match_winrate":        "形勢判断を表示する",
        "match_challenges":     "挑戦状",

        # --- Table headers ---
        "col_player":       "対局者",
        "col_strength":     "棋力",
        "col_time":         "持ち時間",
        "col_komi":         "コミ",

        # --- KifuDialog ---
        "kifu_title":       "棋譜一覧",
        "col_kifu_no":      "棋譜番号",
        "col_date":         "対局日",
        "col_black":        "黒番",
        "col_white":        "白番",
        "col_result":       "勝敗",

        # --- Offer dialog ---
        "offer_arrived":    "挑戦状が届いています！",

        # --- Score calculation ---
        "score_calculating": "計算中です。少しお待ちください...",
        "score_title":       "地合計算",

        # --- Messageboxes ---
        "msg_error":            "エラー",
        "msg_score_fail":       "地合計算に失敗しました:\n{}",
        "msg_connect_fail":     "接続できませんでした: {}",
        "msg_disconnect":       "切断",
        "msg_disconnected":     "相手との接続が切れました",
        "msg_server_disconnect": "サーバーとの接続が切れました",
        "msg_account_created":  "アカウントを作成しました。ログインしてください。",
        "msg_complete":         "完了",

        # --- Promotion popup ---
        "promotion_dan":    "昇段",
        "promotion_kyu":    "昇級",
        "promotion_congrats": "おめでとうございます",
        "promo_template_dan":        "{}さん\n{}に昇段しました\n\nおめでとうございます",
        "promo_template_kyu":        "{}さん\n{}に昇級しました\n\nおめでとうございます",
        "promo_template_dan_noname": "{}に昇段しました\n\nおめでとうございます",
        "promo_template_kyu_noname": "{}に昇級しました\n\nおめでとうございます",

        # --- AI Game ---
        "btn_ai":           "AI対局",
        "ai_dialog_title":  "AI対局設定",
        "ai_difficulty":    "難易度",
        "ai_color":         "あなたの色",
        "ai_black":         "黒番",
        "ai_white":         "白番",
        "ai_start":         "開始",
        "ai_name":          "KataGo AI",
        "ai_thinking":      "AI思考中...",
        "ai_resigned":      "AIが投了しました。\nあなたの勝ちです。",
        "ai_pass":          "AIがパスしました。",
        "ai_not_found":     "KataGoが見つかりません。\nkatagoフォルダを確認してください。",
    },

    "en": {
        # --- Login screen ---
        "login_title":      "Goka GO Login",
        "login_handle":     "Handle Name",
        "login_password":   "Password",
        "login_btn":        "Login",

        # --- Register screen ---
        "reg_title":        "Create Account",
        "reg_realname":     "Full Name",
        "reg_handle":       "Handle Name",
        "reg_password":     "Password (4+ alphanumeric/symbol chars)",
        "reg_password2":    "Confirm Password",
        "reg_rank":         "Rank",
        "reg_btn":          "Create Account",
        "reg_back":         "Back",
        "reg_handle_warn":  "Handle name must be 20 characters or fewer.",

        # --- Toolbar buttons ---
        "btn_game":         "Play",
        "btn_resign":       "Resign",
        "btn_pass":         "Pass",
        "btn_score":        "Score",
        "btn_kifu":         "Records",
        "btn_reset":        "Reset",
        "btn_logout":       "Logout",

        # --- Common buttons ---
        "btn_close":        "Close",
        "btn_accept":       "Accept",
        "btn_decline":      "Decline",
        "btn_reject":       "Reject",
        "btn_cancel":       "Cancel",
        "btn_apply":        "Apply",
        "btn_host":         "Start Offer",
        "btn_show":         "Show",

        # --- Menu: File ---
        "menu_file":        "File(F)",
        "menu_new":         "New(N)",
        "menu_open":        "Open(O)",
        "menu_save":        "Save(S)",
        "menu_saveas":      "Save As(A)",
        "menu_exit":        "Exit(X)",

        # --- Menu: Settings ---
        "menu_settings":    "Settings(G)",
        "menu_speed":       "Playback Speed(S)",
        "menu_language":    "Language(L)",

        # --- Menu: View ---
        "menu_view":        "View(V)",
        "menu_board":       "Board Style",

        # --- Menu: Game ---
        "menu_game":        "Game(P)",
        "menu_game_start":  "Play",
        "menu_resign":      "Resign",
        "menu_pass":        "Pass",
        "menu_score":       "Score",
        "menu_kifu":        "Records",
        "menu_review":      "Review",
        "menu_review_end":  "End Review",

        # --- Menu: Help ---
        "menu_help":        "Help(H)",
        "menu_howto":       "How to Play(*)",
        "menu_features":    "Features(*)",
        "menu_about":       "About(*)",

        # --- Window titles ---
        "title_match_dialog":   "Match Request",
        "title_offer_dialog":   "Match Offer!",
        "title_kifu_dialog":    "Game Records",
        "title_score":          "Score Calculation",
        "title_howto":          "How to Play",
        "title_features":       "Features",
        "title_about":          "About",

        # --- MatchDialog labels ---
        "match_settings":       "Match Settings",
        "match_time":           "Main Time",
        "match_komi":           "Komi",
        "match_byoyomi":        "Byoyomi",
        "match_periods":        "Periods",
        "match_hosting":        "Waiting for opponent...",
        "match_no_opponent":    "No player accepted the match conditions.",
        "match_cancelled":      "Match request cancelled.",
        "match_winrate":        "Show winrate",
        "match_challenges":     "Challenges",

        # --- Table headers ---
        "col_player":       "Player",
        "col_strength":     "Rank",
        "col_time":         "Time",
        "col_komi":         "Komi",

        # --- KifuDialog ---
        "kifu_title":       "Game Records",
        "col_kifu_no":      "No.",
        "col_date":         "Date",
        "col_black":        "Black",
        "col_white":        "White",
        "col_result":       "Result",

        # --- Offer dialog ---
        "offer_arrived":    "You have received a match offer!",

        # --- Score calculation ---
        "score_calculating": "Calculating, please wait...",
        "score_title":       "Score",

        # --- Messageboxes ---
        "msg_error":            "Error",
        "msg_score_fail":       "Score calculation failed:\n{}",
        "msg_connect_fail":     "Connection failed: {}",
        "msg_disconnect":       "Disconnected",
        "msg_disconnected":     "Connection to opponent lost.",
        "msg_server_disconnect": "Connection to server lost.",
        "msg_account_created":  "Account created. Please log in.",
        "msg_complete":         "Done",

        # --- Promotion popup ---
        "promotion_dan":    "promoted to",
        "promotion_kyu":    "promoted to",
        "promotion_congrats": "Congratulations!",
        "promo_template_dan":        "Congratulations!\n{}\nPromoted to {}!",
        "promo_template_kyu":        "Congratulations!\n{}\nAdvanced to {}!",
        "promo_template_dan_noname": "Congratulations!\nPromoted to {}!",
        "promo_template_kyu_noname": "Congratulations!\nAdvanced to {}!",

        # --- AI Game ---
        "btn_ai":           "AI Game",
        "ai_dialog_title":  "AI Game Settings",
        "ai_difficulty":    "Difficulty",
        "ai_color":         "Your Color",
        "ai_black":         "Black",
        "ai_white":         "White",
        "ai_start":         "Start",
        "ai_name":          "KataGo AI",
        "ai_thinking":      "AI thinking...",
        "ai_resigned":      "AI resigned.\nYou win!",
        "ai_pass":          "AI passed.",
        "ai_not_found":     "KataGo not found.\nPlease check the katago folder.",
    },

    "zh": {
        # --- Login screen ---
        "login_title":      "碁华 登录",
        "login_handle":     "昵称",
        "login_password":   "密码",
        "login_btn":        "登录",

        # --- Register screen ---
        "reg_title":        "创建账户",
        "reg_realname":     "姓名",
        "reg_handle":       "昵称",
        "reg_password":     "密码（4位以上字母/数字/符号）",
        "reg_password2":    "确认密码",
        "reg_rank":         "棋力",
        "reg_btn":          "创建账户",
        "reg_back":         "返回",
        "reg_handle_warn":  "昵称不得超过20个字符。",

        # --- Toolbar buttons ---
        "btn_game":         "对局",
        "btn_resign":       "投降",
        "btn_pass":         "停一手",
        "btn_score":        "计算地盘",
        "btn_kifu":         "棋谱",
        "btn_reset":        "初始化",
        "btn_logout":       "退出登录",

        # --- Common buttons ---
        "btn_close":        "关闭",
        "btn_accept":       "接受",
        "btn_decline":      "拒绝",
        "btn_reject":       "拒绝",
        "btn_cancel":       "取消",
        "btn_apply":        "申请对局",
        "btn_host":         "发起申请",
        "btn_show":         "显示",

        # --- Menu: File ---
        "menu_file":        "文件(F)",
        "menu_new":         "新建(N)",
        "menu_open":        "打开(O)",
        "menu_save":        "保存(S)",
        "menu_saveas":      "另存为(A)",
        "menu_exit":        "退出(X)",

        # --- Menu: Settings ---
        "menu_settings":    "设置(G)",
        "menu_speed":       "播放速度(S)",
        "menu_language":    "语言(L)",

        # --- Menu: View ---
        "menu_view":        "显示(V)",
        "menu_board":       "棋盘样式",

        # --- Menu: Game ---
        "menu_game":        "对局(P)",
        "menu_game_start":  "对局",
        "menu_resign":      "投降",
        "menu_pass":        "停一手",
        "menu_score":       "计算地盘",
        "menu_kifu":        "棋谱",
        "menu_review":      "复盘",
        "menu_review_end":  "结束复盘",

        # --- Menu: Help ---
        "menu_help":        "帮助(H)",
        "menu_howto":       "玩法说明(*)",
        "menu_features":    "功能介绍(*)",
        "menu_about":       "版本信息(*)",

        # --- Window titles ---
        "title_match_dialog":   "申请对局",
        "title_offer_dialog":   "收到挑战！",
        "title_kifu_dialog":    "棋谱列表",
        "title_score":          "计算地盘",
        "title_howto":          "玩法说明",
        "title_features":       "功能介绍",
        "title_about":          "版本信息",

        # --- MatchDialog labels ---
        "match_settings":       "对局条件设置",
        "match_time":           "持时",
        "match_komi":           "贴目",
        "match_byoyomi":        "读秒",
        "match_periods":        "次数",
        "match_hosting":        "等待对手中...",
        "match_no_opponent":    "没有玩家接受对局条件。",
        "match_cancelled":      "已取消对局申请。",
        "match_winrate":        "显示形势判断",
        "match_challenges":     "挑战",

        # --- Table headers ---
        "col_player":       "对局者",
        "col_strength":     "棋力",
        "col_time":         "持时",
        "col_komi":         "贴目",

        # --- KifuDialog ---
        "kifu_title":       "棋谱列表",
        "col_kifu_no":      "编号",
        "col_date":         "对局日期",
        "col_black":        "黑方",
        "col_white":        "白方",
        "col_result":       "胜负",

        # --- Offer dialog ---
        "offer_arrived":    "收到挑战书！",

        # --- Score calculation ---
        "score_calculating": "计算中，请稍候...",
        "score_title":       "计算地盘",

        # --- Messageboxes ---
        "msg_error":            "错误",
        "msg_score_fail":       "地盘计算失败:\n{}",
        "msg_connect_fail":     "连接失败: {}",
        "msg_disconnect":       "断线",
        "msg_disconnected":     "与对手的连接已断开。",
        "msg_server_disconnect": "与服务器的连接已断开。",
        "msg_account_created":  "账户已创建，请登录。",
        "msg_complete":         "完成",

        # --- Promotion popup ---
        "promotion_dan":    "晋升为",
        "promotion_kyu":    "晋升为",
        "promotion_congrats": "恭喜！",
        "promo_template_dan":        "{}，\n恭喜升段至{}！\n\n恭喜恭喜！",
        "promo_template_kyu":        "{}，\n恭喜升级至{}！\n\n恭喜恭喜！",
        "promo_template_dan_noname": "恭喜升段至{}！\n\n恭喜恭喜！",
        "promo_template_kyu_noname": "恭喜升级至{}！\n\n恭喜恭喜！",

        # --- AI Game ---
        "btn_ai":           "AI对局",
        "ai_dialog_title":  "AI对局设置",
        "ai_difficulty":    "难度",
        "ai_color":         "你的颜色",
        "ai_black":         "黑棋",
        "ai_white":         "白棋",
        "ai_start":         "开始",
        "ai_name":          "KataGo AI",
        "ai_thinking":      "AI思考中...",
        "ai_resigned":      "AI认输了。\n你赢了！",
        "ai_pass":          "AI跳过了。",
        "ai_not_found":     "未找到KataGo。\n请检查katago文件夹。",
    },

    "ko": {
        # --- Login screen ---
        "login_title":      "고카 GO 로그인",
        "login_handle":     "핸들 이름",
        "login_password":   "비밀번호",
        "login_btn":        "로그인",

        # --- Register screen ---
        "reg_title":        "계정 만들기",
        "reg_realname":     "이름",
        "reg_handle":       "핸들 이름",
        "reg_password":     "비밀번호 (영문/숫자/기호 4자 이상)",
        "reg_password2":    "비밀번호 확인",
        "reg_rank":         "기력",
        "reg_btn":          "계정 만들기",
        "reg_back":         "돌아가기",
        "reg_handle_warn":  "핸들 이름은 20자 이내여야 합니다.",

        # --- Toolbar buttons ---
        "btn_game":         "대국",
        "btn_resign":       "기권",
        "btn_pass":         "패스",
        "btn_score":        "집계산",
        "btn_kifu":         "기보",
        "btn_reset":        "초기화",
        "btn_logout":       "로그아웃",

        # --- Common buttons ---
        "btn_close":        "닫기",
        "btn_accept":       "수락",
        "btn_decline":      "거절",
        "btn_reject":       "거절",
        "btn_cancel":       "취소",
        "btn_apply":        "대국 신청",
        "btn_host":         "신청 시작",
        "btn_show":         "표시",

        # --- Menu: File ---
        "menu_file":        "파일(F)",
        "menu_new":         "새로 만들기(N)",
        "menu_open":        "열기(O)",
        "menu_save":        "저장(S)",
        "menu_saveas":      "다른 이름으로 저장(A)",
        "menu_exit":        "종료(X)",

        # --- Menu: Settings ---
        "menu_settings":    "설정(G)",
        "menu_speed":       "재생 속도(S)",
        "menu_language":    "언어(L)",

        # --- Menu: View ---
        "menu_view":        "보기(V)",
        "menu_board":       "바둑판 선택",

        # --- Menu: Game ---
        "menu_game":        "대국(P)",
        "menu_game_start":  "대국",
        "menu_resign":      "기권",
        "menu_pass":        "패스",
        "menu_score":       "집계산",
        "menu_kifu":        "기보",
        "menu_review":      "검토",
        "menu_review_end":  "검토 종료",

        # --- Menu: Help ---
        "menu_help":        "도움말(H)",
        "menu_howto":       "사용 방법(*)",
        "menu_features":    "기능(*)",
        "menu_about":       "버전 정보(*)",

        # --- Window titles ---
        "title_match_dialog":   "대국 신청",
        "title_offer_dialog":   "대국 신청이 왔습니다!",
        "title_kifu_dialog":    "기보 목록",
        "title_score":          "집계산",
        "title_howto":          "사용 방법",
        "title_features":       "기능",
        "title_about":          "버전 정보",

        # --- MatchDialog labels ---
        "match_settings":       "대국 조건 설정",
        "match_time":           "제한 시간",
        "match_komi":           "덤",
        "match_byoyomi":        "초읽기",
        "match_periods":        "횟수",
        "match_hosting":        "상대를 기다리는 중...",
        "match_no_opponent":    "대국 조건을 수락한 플레이어가 없습니다.",
        "match_cancelled":      "대국 신청을 취소했습니다.",
        "match_winrate":        "형세 판단 표시",
        "match_challenges":     "도전장",

        # --- Table headers ---
        "col_player":       "상대방",
        "col_strength":     "기력",
        "col_time":         "제한 시간",
        "col_komi":         "덤",

        # --- KifuDialog ---
        "kifu_title":       "기보 목록",
        "col_kifu_no":      "번호",
        "col_date":         "대국일",
        "col_black":        "흑",
        "col_white":        "백",
        "col_result":       "결과",

        # --- Offer dialog ---
        "offer_arrived":    "도전장이 도착했습니다!",

        # --- Score calculation ---
        "score_calculating": "계산 중입니다. 잠시 기다려 주세요...",
        "score_title":       "집계산",

        # --- Messageboxes ---
        "msg_error":            "오류",
        "msg_score_fail":       "집계산 실패:\n{}",
        "msg_connect_fail":     "연결 실패: {}",
        "msg_disconnect":       "연결 끊김",
        "msg_disconnected":     "상대와의 연결이 끊겼습니다.",
        "msg_server_disconnect": "서버와의 연결이 끊겼습니다.",
        "msg_account_created":  "계정이 생성되었습니다. 로그인하세요.",
        "msg_complete":         "완료",

        # --- Promotion popup ---
        "promotion_dan":    "단으로 승단",
        "promotion_kyu":    "급으로 승급",
        "promotion_congrats": "축하합니다!",
        "promo_template_dan":        "{}님\n{}에 승단했습니다\n\n축하합니다!",
        "promo_template_kyu":        "{}님\n{}으로 승급했습니다\n\n축하합니다!",
        "promo_template_dan_noname": "{}에 승단했습니다\n\n축하합니다!",
        "promo_template_kyu_noname": "{}으로 승급했습니다\n\n축하합니다!",
    },
}

# Default language
_current_lang = "ja"


def set_language(lang: str):
    global _current_lang
    if lang in STRINGS:
        _current_lang = lang


def get_language() -> str:
    return _current_lang


def L(key: str, *args) -> str:
    """Return the UI string for the given key in the current language.
    Falls back to Japanese if the key is missing in the selected language.
    Use *args for str.format() substitution.
    """
    text = STRINGS.get(_current_lang, {}).get(key) \
        or STRINGS["ja"].get(key) \
        or key
    if args:
        try:
            text = text.format(*args)
        except Exception:
            pass
    return text
