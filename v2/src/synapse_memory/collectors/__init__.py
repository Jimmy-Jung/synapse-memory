"""외부 데이터 수집기.

각 수집기는 외부 소스(Claude Code 로그, Obsidian, Gmail, ...)에서 변경분을
읽어 L0(``~/.synapse/private/raw/``)에 mirror한다. 분류/redaction은 별도 단계.

저자: JunyoungJung <joony300@gmail.com>
"""
