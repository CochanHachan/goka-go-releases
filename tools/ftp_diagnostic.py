#!/usr/bin/env python3
"""FTP diagnostic: check directory structure after login."""
import ftplib
import os
import sys


def main():
    host = os.environ.get("GOKA_FTP_HOST", "")
    user = os.environ.get("GOKA_FTP_USER", "")
    pw = os.environ.get("GOKA_FTP_PASS", "")

    if not host or not user or not pw:
        print("ERROR: missing FTP credentials", file=sys.stderr)
        return 1

    ftp = ftplib.FTP()
    ftp.connect(host, 21, timeout=30)
    ftp.login(user, pw)

    print("HOME:", ftp.pwd())
    print("ROOT listing:")
    ftp.retrlines("LIST")
    print()

    try:
        ftp.cwd("public_html")
        print("public_html PWD:", ftp.pwd())
        print("public_html listing (first 20):")
        lines = []
        ftp.retrlines("LIST", lines.append)
        for line in lines[:20]:
            print(" ", line)
        if len(lines) > 20:
            print(f"  ... ({len(lines)} total)")
        print()

        try:
            ftp.cwd("releases")
            print("releases PWD:", ftp.pwd())
            print("releases listing:")
            rlines = []
            ftp.retrlines("LIST", rlines.append)
            for line in rlines[:20]:
                print(" ", line)
            if len(rlines) > 20:
                print(f"  ... ({len(rlines)} total)")
        except Exception as e:
            print("releases error:", e)
    except Exception as e:
        print("public_html error:", e)

    # Also check if version.json exists at root
    try:
        ftp.cwd("/")
        root_files = []
        ftp.retrlines("NLST", root_files.append)
        if "version.json" in root_files:
            print("\nWARNING: version.json found at FTP root!")
    except Exception:
        pass

    ftp.quit()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
