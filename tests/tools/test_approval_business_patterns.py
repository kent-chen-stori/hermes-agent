"""stori: 业务危险命令规则必须锚定在命令位置，不能因为"提到"就拦。

`DANGEROUS_PATTERNS` 里 stori 自加的 6 条业务规则（archery / xxljob / fundcheck）
原先写成 `\\barchery\\b.*\\bticket\\b.*\\bapprove\\b`——只要命令字符串里出现这几个词
就命中。而 `detect_dangerous_command` 扫的是**整条命令**，包含要发出去的正文，
于是 agent 干完活回群里汇报时：

    lark-cli im +messages-send --chat-id oc_x --markdown "archery ticket approve 已完成"

「发一条消息」这个无害动作也要走审批。同理 echo、grep、写文档里引用命令名都会误伤。
claw-pro 上这个群天天干 archery/xxljob/fundcheck 的活，误拦是常态。

改成锚定 `_CMDPOS`（行首 / 命令分隔符后 / 子 shell 开头 / sudo·env·exec 包装后），
和同文件里 shutdown/reboot/rm 那几条硬拦截用的是同一个片段。

这个文件在 stori 分支自有，不和上游测试文件抢 merge——上游对这 6 条规则本来就
零覆盖（`grep archery tests/` 全空），这正是它们一直写得过宽没人发现的原因。
"""

import pytest

from tools.approval import detect_dangerous_command


# 真正会执行的写法，必须拦住
MUST_INTERCEPT = [
    "archery ticket approve 56961",
    "archery ticket execute 56961",
    "xxljob trigger 123",
    "fundcheck rule-new --id 1",
    "fundcheck rule-update --id 1",
    "fundcheck rule-switch-status --id 1",
    # 命令分隔符之后仍在命令位置
    "cd /tmp && archery ticket approve 56961",
    "echo y | archery ticket approve 56961",
    "x=1; archery ticket approve 56961",
    # 包装命令
    "sudo archery ticket approve 56961",
    "env FOO=1 archery ticket approve 56961",
    "nohup archery ticket approve 56961",
    # 命令替换 / 子 shell
    "$(archery ticket approve 56961)",
    "(archery ticket approve 56961)",
]

# 只是把命令名当文本传递，不该拦
MUST_ALLOW = [
    'lark-cli im +messages-send --chat-id oc_1 --markdown "archery ticket approve 已完成"',
    'lark-cli im +messages-send --chat-id oc_1 --markdown "xxljob trigger 已触发"',
    'lark-cli im +messages-send --chat-id oc_1 --markdown "fundcheck rule-update 已更新"',
    'lark-cli docx +blocks-create --content "步骤：archery ticket approve"',
    'echo "archery ticket approve"',
    'grep -rn "fundcheck rule-new" .',
]


@pytest.mark.parametrize("command", MUST_INTERCEPT)
def test_real_invocation_still_intercepted(command):
    is_dangerous, _key, description = detect_dangerous_command(command)
    assert is_dangerous, f"真实执行没被拦住：{command}"
    assert description


@pytest.mark.parametrize("command", MUST_ALLOW)
def test_mentioning_command_name_is_not_intercepted(command):
    is_dangerous, _key, description = detect_dangerous_command(command)
    assert not is_dangerous, (
        f"只是提到命令名却被拦：{command}\n命中规则：{description}"
    )


def test_slack_block_descriptions_unchanged():
    """描述文案是 SLACK_BLOCKED_PATTERNS 的匹配键，锚定改造不能动它。"""
    from tools.approval import SLACK_BLOCKED_PATTERNS

    for command in (
        "archery ticket approve 56961",
        "archery ticket execute 56961",
        "xxljob trigger 123",
        "fundcheck rule-new --id 1",
        "fundcheck rule-update --id 1",
        "fundcheck rule-switch-status --id 1",
    ):
        _is_dangerous, _key, description = detect_dangerous_command(command)
        assert description in SLACK_BLOCKED_PATTERNS, (
            f"{command!r} 的描述 {description!r} 不在 SLACK_BLOCKED_PATTERNS 里，"
            "Slack 硬拦截会失效"
        )
