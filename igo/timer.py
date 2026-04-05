# -*- coding: utf-8 -*-
"""碁華 秒読みタイマー"""


class ByoyomiTimer:
    """Manages main time + byoyomi for one player."""
    def __init__(self, main_seconds=600, byo_seconds=30, byo_periods=5):
        self.main_time = main_seconds
        self.byo_time = byo_seconds
        self.byo_periods = byo_periods  # 0 = infinite
        self.remaining = main_seconds
        self.byo_remaining = byo_seconds
        self.byo_periods_left = byo_periods
        self.in_byoyomi = False
        self.expired = False

    def tick(self):
        """Called every second. Returns True if still alive."""
        if self.expired:
            return False
        if not self.in_byoyomi:
            self.remaining -= 1
            if self.remaining <= 0:
                self.remaining = 0
                self.in_byoyomi = True
                self.byo_remaining = self.byo_time
                self.byo_periods_left = self.byo_periods
        else:
            self.byo_remaining -= 1
            if self.byo_remaining <= 0:
                if self.byo_periods == 0:
                    # infinite byoyomi - reset
                    self.byo_remaining = self.byo_time
                else:
                    self.byo_periods_left -= 1
                    if self.byo_periods_left <= 0:
                        self.expired = True
                        return False
                    self.byo_remaining = self.byo_time
        return True

    def on_move(self):
        """Called when the player makes a move. Resets byoyomi clock."""
        if self.in_byoyomi:
            self.byo_remaining = self.byo_time

    def display_text(self):
        """Return display string for the timer."""
        if self.expired:
            return "\u6642\u9593\u5207\u308c"
        if not self.in_byoyomi:
            m = self.remaining // 60
            s = self.remaining % 60
            return "{:d}:{:02d}".format(m, s)
        else:
            if self.byo_periods == 0:
                return "\u79d2\u8aad\u307f {:d}\u79d2".format(self.byo_remaining)
            else:
                return "\u79d2\u8aad\u307f {:d}\u79d2 (\u6b8b{:d}\u56de)".format(
                    self.byo_remaining, self.byo_periods_left)

