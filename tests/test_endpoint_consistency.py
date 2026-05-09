# -*- coding: utf-8 -*-
"""デグレ防止: ステージング/本番のサーバー接続先 URL が
``igo/constants.py`` (テストアプリ・本番アプリが見る URL) と
``igo_admin.py`` (管理者画面が見る URL) で完全一致していること。

両者がずれると、テストアプリは A サーバーの DB に書き込み、
管理者画面は B サーバーの DB を読む、という split-brain が発生し、
登録したユーザーが管理画面に出ない / ログインできない、といった
症状が出る (2026-05-09 yumi/key/Roy インシデント)。

このテストが落ちた場合は両ファイルを揃えること。片側だけ更新するのは禁止。
"""

import ast
import os
import unittest


REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))


def _extract_dict_assign(source: str, var_name: str) -> dict:
    """ソース中のトップレベル ``var_name = {...}`` を辞書として抽出する。

    値がリテラル ``http://...`` や bool/None など ast.literal_eval 可能なものに
    限られている前提。ネスト辞書もそのまま再帰的にデコードする。
    """
    tree = ast.parse(source)
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == var_name:
                    return ast.literal_eval(node.value)
    raise AssertionError(
        "Top-level assignment {!r} not found".format(var_name)
    )


def _read(path: str) -> str:
    with open(os.path.join(REPO_ROOT, path), "r", encoding="utf-8") as f:
        return f.read()


class TestEndpointConsistency(unittest.TestCase):
    """テストアプリと管理者画面が同じサーバーを見るかを確認する。"""

    def setUp(self):
        self.client_cfg = _extract_dict_assign(
            _read("igo/constants.py"), "_CONFIG"
        )
        self.admin_cfg = _extract_dict_assign(
            _read("igo_admin.py"), "_ADMIN_SERVER_CONFIG"
        )

    def test_envs_match(self):
        """両ファイルが同じ環境キー集合を持つこと (production/staging)。"""
        self.assertEqual(
            set(self.client_cfg.keys()),
            set(self.admin_cfg.keys()),
            "_CONFIG (igo/constants.py) と _ADMIN_SERVER_CONFIG (igo_admin.py) "
            "の環境キーが一致しません",
        )

    def test_api_base_url_matches_per_env(self):
        """各環境について api_base_url が完全一致すること。"""
        for env in self.client_cfg:
            client_url = self.client_cfg[env]["api_base_url"]
            admin_url = self.admin_cfg[env]["api_base_url"]
            self.assertEqual(
                client_url,
                admin_url,
                "{env}: igo/constants.py の api_base_url={client_url!r} と "
                "igo_admin.py の api_base_url={admin_url!r} が食い違っています。"
                "両者は必ず同じサーバーを指してください。"
                .format(env=env, client_url=client_url, admin_url=admin_url),
            )

    def test_cloud_server_url_consistent_with_api_base(self):
        """ゲームクライアントの WebSocket URL (cloud_server_url) と
        REST URL (api_base_url) が同じホストを指すこと。"""
        for env, cfg in self.client_cfg.items():
            api = cfg["api_base_url"]
            ws = cfg["cloud_server_url"]
            api_host = api.split("://", 1)[-1]
            ws_host = ws.split("://", 1)[-1]
            self.assertEqual(
                api_host,
                ws_host,
                "{env}: api_base_url={api!r} と cloud_server_url={ws!r} "
                "のホスト/ポートが一致しません".format(env=env, api=api, ws=ws),
            )


if __name__ == "__main__":
    unittest.main()
