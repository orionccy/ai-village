"""
============================================================
locations.py — 地点定义模块
============================================================
定义小镇中的所有地点。每个地点有：
- 名称、类型、坐标范围
- 图标 (emoji)
- 用途标签（哪些活动适合在这里做）

地图坐标规则：
- 原点 (0,0) 在左上角
- x 轴向右增长，y 轴向下增长
- 每个地点占一个矩形区域，由 (x1,y1)-(x2,y2) 定义
============================================================
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Location:
    """
    一个地点的数据模型。

    Attributes:
        id: 唯一标识符，如 "park"
        name: 中文名称，如 "公园"
        emoji: 在地图上显示的图标
        color: Canvas 填充色 (CSS 颜色)
        x1, y1: 左上角坐标
        x2, y2: 右下角坐标（包含）
        activities: 适合在此地做的活动列表
        is_public: 是否为公共区域
    """

    id: str
    name: str
    emoji: str
    color: str
    x1: int
    y1: int
    x2: int
    y2: int
    activities: list[str] = field(default_factory=list)
    is_public: bool = True

    def contains(self, x: int, y: int) -> bool:
        """判断坐标 (x, y) 是否在此地点的范围内。"""
        return self.x1 <= x <= self.x2 and self.y1 <= y <= self.y2

    @property
    def cells(self) -> list[tuple[int, int]]:
        """返回此地点包含的所有格子坐标。"""
        return [
            (x, y)
            for x in range(self.x1, self.x2 + 1)
            for y in range(self.y1, self.y2 + 1)
        ]


# ============================================================
# 地点注册表
# ============================================================

# 按照地图布局定义每个地点的精确坐标范围
# 参考规划文档中的 ASCII 地图

LOCATIONS: dict[str, Location] = {
    # ---- 住宅区 ----
    "residential_a": Location(
        id="residential_a",
        name="住宅区 A",
        emoji="🏠",
        color="#c9a96e",  # 浅棕
        x1=0, y1=0, x2=2, y2=1,
        activities=["回家", "休息"],
        is_public=False,
    ),
    "residential_b": Location(
        id="residential_b",
        name="住宅区 B",
        emoji="🏠",
        color="#c9a96e",
        x1=1, y1=3, x2=2, y2=4,
        activities=["回家", "休息"],
        is_public=False,
    ),
    "residential_c": Location(
        id="residential_c",
        name="住宅区 C",
        emoji="🏠",
        color="#c9a96e",
        x1=0, y1=6, x2=1, y2=7,
        activities=["回家", "休息"],
        is_public=False,
    ),
    "residential_d": Location(
        id="residential_d",
        name="住宅区 D",
        emoji="🏠",
        color="#c9a96e",
        x1=8, y1=6, x2=9, y2=7,
        activities=["回家", "休息"],
        is_public=False,
    ),

    # ---- 公共区域 ----
    "park": Location(
        id="park",
        name="公园",
        emoji="🌳",
        color="#4caf50",  # 绿色
        x1=4, y1=0, x2=5, y2=2,
        activities=["散步", "聊天", "休息", "运动", "读书"],
        is_public=True,
    ),
    "market": Location(
        id="market",
        name="市场",
        emoji="🏪",
        color="#ff9800",  # 橙色
        x1=7, y1=0, x2=8, y2=1,
        activities=["购物", "工作", "偶遇"],
        is_public=True,
    ),
    "cafe": Location(
        id="cafe",
        name="咖啡馆",
        emoji="☕",
        color="#795548",  # 棕色
        x1=7, y1=3, x2=8, y2=4,
        activities=["聊天", "读书", "休息", "约会"],
        is_public=True,
    ),
    "plaza": Location(
        id="plaza",
        name="广场",
        emoji="🎨",
        color="#5c6bc0",  # 浅蓝
        x1=4, y1=4, x2=5, y2=4,
        activities=["活动", "聚会", "工作", "表演"],
        is_public=True,
    ),
    "fountain": Location(
        id="fountain",
        name="喷泉",
        emoji="⛲",
        color="#42a5f5",  # 蓝色
        x1=4, y1=7, x2=5, y2=8,
        activities=["约会", "思考", "休息", "散步"],
        is_public=True,
    ),
}


# ============================================================
# 工具函数
# ============================================================

def get_location_at(x: int, y: int) -> Optional[Location]:
    """
    返回坐标 (x, y) 所在的地点。
    如果该坐标不属于任何已定义地点，返回 None（表示普通道路/空地）。
    """
    for loc in LOCATIONS.values():
        if loc.contains(x, y):
            return loc
    return None


def get_location_name_at(x: int, y: int) -> str:
    """
    返回坐标 (x, y) 所在的地名。
    用于 Agent 感知时描述"我现在在哪"。

    示例:
        >>> get_location_name_at(4, 0)
        '公园'
        >>> get_location_name_at(0, 9)
        '空地'
    """
    loc = get_location_at(x, y)
    return loc.name if loc else "空地"


def get_location_by_id(location_id: str) -> Optional[Location]:
    """按 ID 查找地点。"""
    return LOCATIONS.get(location_id)


def get_all_public_locations() -> list[Location]:
    """获取所有公共地点的列表。"""
    return [loc for loc in LOCATIONS.values() if loc.is_public]


def get_nearest_location(x: int, y: int) -> Location:
    """
    返回距离坐标 (x, y) 最近的地点（曼哈顿距离）。
    如果当前位置就在某地点内，返回该地点。
    """
    loc = get_location_at(x, y)
    if loc:
        return loc

    best = None
    best_dist = float("inf")
    for location in LOCATIONS.values():
        # 计算到地点中心点的曼哈顿距离
        cx = (location.x1 + location.x2) // 2
        cy = (location.y1 + location.y2) // 2
        dist = abs(x - cx) + abs(y - cy)
        if dist < best_dist:
            best_dist = dist
            best = location

    return best  # type: ignore
