"""Small tree renderer; continuation lines retain their ancestor guides."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class TreeNode:
    lines: list[str]
    children: list[TreeNode] = field(default_factory=list)


def render_tree(nodes: list[TreeNode], prefix: str = "  ") -> list[str]:
    output = []
    for index, node in enumerate(nodes):
        last = index == len(nodes) - 1
        connector = "└─ " if last else "├─ "
        continuation = "   " if last else "│  "
        if not node.lines:
            continue
        output.append(prefix + connector + node.lines[0])
        output.extend(prefix + continuation + line for line in node.lines[1:])
        output.extend(render_tree(node.children, prefix + continuation))
    return output
