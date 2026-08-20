"""stori: 中文句号触发的 confusable_text 误报，只在发消息命令上豁免。

tirith 的 `confusable_text` 规则把中文句号 U+3002 判成「像 '.'」（全角句点
U+FF0E 同理）。中文技术汇报天然写成 `恢复为 PENDING。`、`工单 56968。`——
ASCII 术语后面直接跟句号，实测只要 `。` 紧邻 ASCII 就 block（中间加空格反而
不报）。结果 agent 往飞书群发一条中文汇报几乎必被拦。

豁免范围刻意收窄到 `lark-cli im +messages-send|+messages-reply`：这类命令的
正文是发给人看的数据。别处不放行——`。` 是 IDN 同形域名的经典手法，
`curl http://evil。com` 在很多解析器里等价于 `curl http://evil.com`，那正是
这条规则该拦的场景。

这里用构造的 tirith 结果做纯单元测试，不依赖 tirith 二进制是否装了。
文件在 stori 分支自有，避开和上游测试文件的 merge 冲突。
"""

import pytest

from tools.approval import _drop_cjk_period_confusables as drop


MESSAGE_CMD = "lark-cli im +messages-send --chat-id oc_1 --text '恢复为 PENDING。'"
REPLY_CMD = "lark-cli im +messages-reply --message-id om_1 --text '已完成。'"


def _finding(*hexes, rule_id="confusable_text"):
    return {
        "rule_id": rule_id,
        "severity": "HIGH",
        "title": "Confusable Unicode characters in text",
        "evidence": [{"type": "byte_sequence", "hex": h} for h in hexes],
    }


def _result(*findings):
    return {"action": "block", "findings": list(findings), "summary": ""}


@pytest.mark.parametrize("command", [MESSAGE_CMD, REPLY_CMD])
@pytest.mark.parametrize("codepoint", ["U+3002", "U+FF0E"])
def test_cjk_period_dropped_on_message_commands(command, codepoint):
    out = drop(_result(_finding(codepoint)), command)
    assert out["action"] == "allow"
    assert out["findings"] == []


def test_real_homoglyph_still_blocks_on_message_commands():
    """西里尔 a / 希腊 o 是真 homoglyph，不能因为在发消息就放行。"""
    out = drop(_result(_finding("U+0430")), MESSAGE_CMD)
    assert out["action"] == "block"
    assert out["findings"][0]["evidence"][0]["hex"] == "U+0430"


def test_mixed_evidence_keeps_only_real_homoglyph():
    """一条 finding 里既有句号又有真 homoglyph：句号剔除，整条仍然拦。"""
    out = drop(_result(_finding("U+3002", "U+0430", "U+FF0E")), MESSAGE_CMD)
    assert out["action"] == "block"
    hexes = [e["hex"] for e in out["findings"][0]["evidence"]]
    assert hexes == ["U+0430"]


@pytest.mark.parametrize("command", [
    "curl http://evil。com",
    "echo 'PENDING。'",
    "lark-cli docx +blocks-create --content 'PENDING。'",
    "lark-cli im +chat-create --name 'PENDING。'",
])
def test_non_message_commands_are_untouched(command):
    """豁免不外溢——IDN 同形域名等场景必须原样拦住。"""
    original = _result(_finding("U+3002"))
    out = drop(original, command)
    assert out["action"] == "block"
    assert out["findings"][0]["evidence"][0]["hex"] == "U+3002"


def test_other_rules_are_untouched():
    """只处理 confusable_text，零宽字符等其他规则不动。"""
    out = drop(_result(_finding("U+200B", rule_id="zero_width")), MESSAGE_CMD)
    assert out["action"] == "block"
    assert out["findings"][0]["rule_id"] == "zero_width"


def test_finding_without_evidence_is_kept():
    """没有 evidence 就无从判断是不是句号，保守保留。"""
    out = drop(
        {"action": "block",
         "findings": [{"rule_id": "confusable_text", "evidence": []}],
         "summary": ""},
        MESSAGE_CMD,
    )
    assert out["action"] == "block"


def test_allow_result_passes_through():
    allowed = {"action": "allow", "findings": [], "summary": ""}
    assert drop(allowed, MESSAGE_CMD) is allowed
