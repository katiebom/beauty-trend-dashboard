"""
대시보드 사용자 관리 CLI
─────────────────────────────────────────────────────────────────
사용법:
  python3 scripts/manage_users.py add <username> <email> <name> [<role>]
  python3 scripts/manage_users.py change_password <username>
  python3 scripts/manage_users.py remove <username>
  python3 scripts/manage_users.py list
─────────────────────────────────────────────────────────────────
"""
import sys
import yaml
import bcrypt
import getpass
from pathlib import Path

CONFIG = Path(__file__).parent.parent / "config" / "auth_config.yaml"


def load():
    with open(CONFIG, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def save(data):
    with open(CONFIG, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False)


def hash_pw(pw: str) -> str:
    return bcrypt.hashpw(pw.encode(), bcrypt.gensalt()).decode()


def add_user(username: str, email: str, name: str, role: str = "viewer"):
    data = load()
    creds = data.setdefault("credentials", {}).setdefault("usernames", {})
    if username in creds:
        print(f"❌ '{username}' 이미 존재합니다. change_password 사용.")
        return
    pw = getpass.getpass(f"새 비밀번호 ({username}): ")
    pw2 = getpass.getpass("비밀번호 확인: ")
    if pw != pw2:
        print("❌ 비밀번호가 일치하지 않습니다.")
        return
    if len(pw) < 8:
        print("❌ 비밀번호는 최소 8자 이상이어야 합니다.")
        return
    from datetime import date
    creds[username] = {
        "name": name,
        "email": email,
        "password": hash_pw(pw),
        "role": role,
        "created_at": date.today().isoformat(),
    }
    save(data)
    print(f"✅ '{username}' ({name}, {role}) 추가 완료. 이메일: {email}")


def change_password(username: str):
    data = load()
    creds = data.get("credentials", {}).get("usernames", {})
    if username not in creds:
        print(f"❌ '{username}' 없음")
        return
    pw = getpass.getpass(f"새 비밀번호 ({username}): ")
    pw2 = getpass.getpass("비밀번호 확인: ")
    if pw != pw2 or len(pw) < 8:
        print("❌ 비밀번호 불일치 또는 8자 미만")
        return
    creds[username]["password"] = hash_pw(pw)
    save(data)
    print(f"✅ '{username}' 비밀번호 변경 완료")


def remove_user(username: str):
    data = load()
    creds = data.get("credentials", {}).get("usernames", {})
    if username not in creds:
        print(f"❌ '{username}' 없음")
        return
    if username == "katie":
        confirm = input("⚠️ 'katie'(admin) 삭제? 'YES' 입력: ")
        if confirm != "YES":
            print("취소됨")
            return
    del creds[username]
    save(data)
    print(f"✅ '{username}' 삭제 완료")


def list_users():
    data = load()
    creds = data.get("credentials", {}).get("usernames", {})
    print(f"\n총 {len(creds)}명 등록")
    print("─" * 70)
    for username, info in creds.items():
        role = info.get("role", "viewer")
        emoji = "👑" if role == "admin" else "👤"
        print(f"  {emoji} {username:<15} {info.get('name','?'):<15} "
              f"{info.get('email',''):<30} [{role}]  생성: {info.get('created_at','?')}")
    print()


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return
    cmd = sys.argv[1]
    if cmd == "add":
        if len(sys.argv) < 5:
            print("사용: add <username> <email> <name> [<role>]")
            return
        add_user(sys.argv[2], sys.argv[3], sys.argv[4],
                 sys.argv[5] if len(sys.argv) > 5 else "viewer")
    elif cmd == "change_password":
        change_password(sys.argv[2])
    elif cmd == "remove":
        remove_user(sys.argv[2])
    elif cmd == "list":
        list_users()
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
