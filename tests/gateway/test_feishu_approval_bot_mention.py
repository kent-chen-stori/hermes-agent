"""stori: 飞书审批卡片不得把 required_user 绑到机器人身上。

`gateway/run.py` 的 `_approval_notify_sync` 给飞书审批卡片填 `user_id`，这个值
一value两用：卡片里 `<at>` 谁，以及之后只有谁点得动按钮（adapter 侧的
`required_user` 校验）。群里的告警 bot 推一条消息就会起 agent turn
（`feishu.allow_bots=mentions`），兜底逻辑会把卡片绑到机器人的 open_id —— 机器人
不会点按钮，于是审批彻底点不动，人点了被静默拒绝，agent 卡到超时。

生产上真实发生过两次（claw-pro gateway.log）：

    08-15 Approval 163 rejected: clicker ou_65848c76 != required ou_1503...
    08-16 Approval 178 rejected: clicker ou_95fe4f4d != required ou_1503...

`ou_1503...` 是"线上问题助手"告警机器人。两条后面都没有任何 resolved 记录。

这里用 AST 结构断言而不是调用 `_approval_notify_sync`（它是个闭包，拿不到），
思路和 tests/gateway/test_approval_prompt_redaction.py 一致：改动被重构掉时失败，
被无害地挪动时不失败。单独成文件是为了不和上游的测试文件抢 merge。
"""

import ast
import inspect

import gateway.run as run


def _find_notify_fn() -> ast.FunctionDef:
    tree = ast.parse(inspect.getsource(run))
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "_approval_notify_sync":
            return node
    raise AssertionError("_approval_notify_sync not found in gateway.run")


class TestFeishuApprovalBotGuard:
    def test_fallback_branch_excludes_bot_senders(self):
        """兜底分支（source.user_id）必须带 is_bot 判断。"""
        source = inspect.getsource(run)
        notify = _find_notify_fn()

        # 定位 `_approval_extra["user_id"] = source.user_id` 这条兜底赋值
        guarded_if = None
        for node in ast.walk(notify):
            if not isinstance(node, ast.If):
                continue
            for stmt in node.body:
                if not isinstance(stmt, ast.Assign):
                    continue
                target = ast.get_source_segment(source, stmt.targets[0]) or ""
                value = ast.get_source_segment(source, stmt.value) or ""
                if "_approval_extra" in target and "user_id" in target and value.strip() == "source.user_id":
                    guarded_if = node
                    break
            if guarded_if is not None:
                break

        assert guarded_if is not None, (
            "没找到 `_approval_extra[\"user_id\"] = source.user_id` 兜底赋值 —— "
            "审批卡片的 @ 兜底逻辑被改动了，请确认机器人仍被排除"
        )

        condition = ast.get_source_segment(source, guarded_if.test) or ""
        assert "is_bot" in condition, (
            "兜底分支必须排除机器人发起人，否则 required_user 会绑到不会点按钮的 "
            f"bot 上，审批死锁到超时。当前条件：{condition!r}"
        )

    def test_explicit_feishu_user_id_still_wins(self):
        """显式 --feishu-user-id 是人为意图，不受 is_bot 影响（优先级在前）。"""
        source = inspect.getsource(run)
        notify = _find_notify_fn()

        for node in ast.walk(notify):
            if not isinstance(node, ast.If):
                continue
            condition = ast.get_source_segment(source, node.test) or ""
            if "_fuid_match" not in condition:
                continue
            # 显式分支本身不该带 is_bot 判断
            assert "is_bot" not in condition
            # 且必须是 if/elif 的前半段，兜底在 orelse 里
            assert node.orelse, "显式分支后面必须跟着兜底分支"
            return

        raise AssertionError("没找到 --feishu-user-id 显式分支")
