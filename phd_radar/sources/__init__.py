"""信息源集合。导入即完成注册。"""

from .academic_transfer import AcademicTransferSource
from .base import BaseSource, build_source
from .gepris import GeprisSource
from .jobs_ac_uk import JobsAcUkSource
from .nwo import NwoSource
from .ukri import UkriSource
from .uni_page import UniPageSource

__all__ = [
    "BaseSource",
    "build_source",
    "AcademicTransferSource",
    "GeprisSource",
    "JobsAcUkSource",
    "NwoSource",
    "UkriSource",
    "UniPageSource",
]
