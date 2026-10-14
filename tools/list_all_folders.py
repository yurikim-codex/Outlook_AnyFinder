r"""
list_all_folders.py — Outlook 전체 스토어/폴더 인벤토리 (Track B 실측: 보낸 편지함 0건 규명)

목적:
  사용자 Outlook에는 Stores가 4개 있고, 기본 스토어의 "보낸 편지함"(folder id 5)이 0건이다.
  실제 보낸 메일이 다른 계정 스토어에 있는지 확인해, 동기화 대상 폴더 [6, 5] 고정 방식의
  구조적 한계를 규명한다.

실행 (사용자 PC):
  python tools\list_all_folders.py

출력:
  스토어별 표시명 / 각 스토어의 최상위 폴더 전체 (이름 · 기본 폴더 타입 · Items.Count)
  + 기본 받은 편지함(6) · 기본 보낸 편지함(5)의 Items.Count 요약

주의: Outlook 프로세스가 실행 중이어야 한다. 읽기 전용 조사만 수행한다.
"""

import sys

FOLDER_TYPE_NAMES = {
    0: "없음(일반)",
    1: "캘린더",
    2: "연락처",
    3: "작업",
    4: "메모",
    5: "받은 편지함(기본 아님 주의)",  # olFolderInbox 상수는 6 — 여기는 DefaultItemType 계열
    6: "받은 편지함",
    9: "보낸 편지함(기본 아님 주의)",
}


def _count(folder):
    try:
        return folder.Items.Count
    except Exception as e:  # noqa: BLE001 — 조사 스크립트, 개별 폴더 실패 허용
        return f"ERR({e})"


def main():
    import win32com.client  # 지연 import — 비 Windows 환경 문법검사에 영향 없음

    ns = win32com.client.Dispatch("Outlook.Application").GetNamespace("MAPI")

    print("=" * 72)
    print("기본 폴더 요약")
    print("=" * 72)
    for fid, label in ((6, "기본 받은 편지함"), (5, "기본 보낸 편지함")):
        try:
            f = ns.GetDefaultFolder(fid)
            print(f"  [{fid}] {label}: '{f.Name}' → {_count(f)}건  (Store: {f.Store.DisplayName})")
        except Exception as e:  # noqa: BLE001
            print(f"  [{fid}] {label}: 조회 실패 — {e}")

    print()
    print("=" * 72)
    print(f"전체 스토어 인벤토리 (총 {ns.Stores.Count}개)")
    print("=" * 72)
    for si in range(1, ns.Stores.Count + 1):
        store = ns.Stores.Item(si)
        try:
            root = store.GetRootFolder()
            print(f"\n── Store {si}: {store.DisplayName}")
            print(f"   FilePath: {getattr(store, 'FilePath', '(n/a)')}")
            for fi in range(1, root.Folders.Count + 1):
                folder = root.Folders.Item(fi)
                try:
                    dtype = folder.DefaultItemType
                    dname = FOLDER_TYPE_NAMES.get(dtype, str(dtype))
                except Exception:  # noqa: BLE001
                    dname = "?"
                print(f"   [폴더] '{folder.Name}' | 타입={dname} | {_count(folder)}건")
        except Exception as e:  # noqa: BLE001
            print(f"\n── Store {si}: {store.DisplayName} → 열기 실패: {e}")

    print("\nDONE — 위 출력을 그대로 보고하세요.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
