# 자리표시자(placeholder)

`tauri.conf.json`의 `bundle.resources` 글로브(`resources/sidecar/**/*`)는 매칭 파일이
0개면 cargo build가 실패한다(fresh clone에서 Step 1 cargo test 불가 — Track B 실측).
이를 막기 위해 이 파일을 커밋해 둔다.

실제 사이드카 빌드(`sidecar\build_sidecar.ps1`) 시 이 디렉터리는 통째로 삭제되고
빌드 산출물(PyInstaller onedir)로 교체되므로 릴리스 번들에는 영향이 없다.
