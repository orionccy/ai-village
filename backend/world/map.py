"""
============================================================
map.py — 地图网格模块
============================================================
负责管理 2D 网格地图上的空间逻辑：
- 判断坐标是否在地图范围内
- 碰撞检测（两个 Agent 是否在同一格）
- 邻近查询（某格周围有哪些 Agent）
- Agent 位置注册表（谁在哪）

设计原则：
- 地图本身是无状态的，只提供空间判断方法
- Agent 位置通过 AgentManager 管理，map 只做纯函数式查询
============================================================
"""

from backend.config import MAP_WIDTH, MAP_HEIGHT, AGENT_PERCEPTION_RANGE, NEARBY_DISTANCE


def is_valid_cell(x: int, y: int) -> bool:
    """
    判断 (x, y) 是否在地图范围内的合法格子。

    Args:
        x: X 坐标
        y: Y 坐标

    Returns:
        True 如果坐标在地图内

    Examples:
        >>> is_valid_cell(0, 0)
        True
        >>> is_valid_cell(9, 9)
        True
        >>> is_valid_cell(-1, 5)
        False
        >>> is_valid_cell(10, 5)
        False
    """
    return 0 <= x < MAP_WIDTH and 0 <= y < MAP_HEIGHT


def manhattan_distance(x1: int, y1: int, x2: int, y2: int) -> int:
    """
    计算两点之间的曼哈顿距离。

    因为我们只允许上下左右移动（不能斜走），
    所以用曼哈顿距离而非欧几里得距离。

    Examples:
        >>> manhattan_distance(0, 0, 3, 4)
        7
        >>> manhattan_distance(5, 5, 5, 5)
        0
    """
    return abs(x1 - x2) + abs(y1 - y2)


def is_adjacent(x1: int, y1: int, x2: int, y2: int) -> bool:
    """
    判断两个格子是否相邻（距离 ≤ NEARBY_DISTANCE）。

    用于判断两个 Agent 是否可以对话。

    Examples:
        >>> is_adjacent(3, 3, 3, 4)   # 相邻
        True
        >>> is_adjacent(0, 0, 5, 5)   # 很远
        False
    """
    return manhattan_distance(x1, y1, x2, y2) <= NEARBY_DISTANCE


def is_within_perception(ax: int, ay: int, bx: int, by: int) -> bool:
    """
    判断 Agent B 是否在 Agent A 的感知范围内。

    感知范围 = AGENT_PERCEPTION_RANGE 格（曼哈顿距离）。

    Examples:
        >>> is_within_perception(5, 5, 7, 5)   # 距离 2，在范围内
        True
        >>> is_within_perception(0, 0, 8, 8)   # 距离 16，太远
        False
    """
    return manhattan_distance(ax, ay, bx, by) <= AGENT_PERCEPTION_RANGE


def get_adjacent_cells(x: int, y: int) -> list[tuple[int, int]]:
    """
    获取 (x, y) 周围可移动到的合法格子（上下左右 + 停留）。

    不包含"停留"时由调用方决定是否加入原坐标。
    这里只返回 4 个方向的相邻格中合法的那些。

    Returns:
        [(x, y-1), (x+1, y), (x, y+1), (x-1, y)] 中合法的部分

    Examples:
        >>> get_adjacent_cells(5, 5)
        [(5, 4), (6, 5), (5, 6), (4, 5)]

        >>> get_adjacent_cells(0, 0)  # 角落
        [(0, 1), (1, 0)]
    """
    directions = [
        (x, y - 1),  # 上
        (x + 1, y),  # 右
        (x, y + 1),  # 下
        (x - 1, y),  # 左
    ]
    return [(nx, ny) for nx, ny in directions if is_valid_cell(nx, ny)]


def get_move_direction(from_x: int, from_y: int, to_x: int, to_y: int) -> str:
    """
    根据起始和目标坐标，返回移动方向的中文描述。

    用于将 map 层面的坐标变化翻译为 LLM 能理解的"向上/下/左/右"。

    Examples:
        >>> get_move_direction(5, 5, 5, 4)
        '向上'
        >>> get_move_direction(5, 5, 6, 5)
        '向右'
        >>> get_move_direction(5, 5, 5, 5)
        '停留'
    """
    dx = to_x - from_x
    dy = to_y - from_y

    if dx == 0 and dy == 0:
        return "停留"
    if abs(dx) > abs(dy):
        return "向右" if dx > 0 else "向左"
    else:
        return "向下" if dy > 0 else "向上"


def resolve_collision(
    desired_positions: dict[str, tuple[int, int]],
    current_positions: dict[str, tuple[int, int]],
    occupied_cells: set[tuple[int, int]],
) -> dict[str, tuple[int, int]]:
    """
    解决多个 Agent 同时移动时的位置冲突。

    规则：先到先得 (FIFO)。
    如果 Agent 的目标格已被其他人占据，则退回到原位置。

    Args:
        desired_positions: {agent_id: (target_x, target_y)} 每个 Agent 想去的坐标
        current_positions: {agent_id: (current_x, current_y)} 当前坐标
        occupied_cells: 已经被占用的格子集合

    Returns:
        {agent_id: (final_x, final_y)} 解决冲突后的最终坐标
    """
    final = {}
    newly_occupied = set(occupied_cells)

    for agent_id, target in desired_positions.items():
        if target not in newly_occupied:
            # 目标格没人，移动成功
            final[agent_id] = target
            newly_occupied.add(target)
            # 释放原来占的格子
            newly_occupied.discard(current_positions.get(agent_id))
        else:
            # 目标格已被占据，退回原地
            final[agent_id] = current_positions.get(agent_id, target)

    return final
