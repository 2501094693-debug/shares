"""个股四价极值分析。



- ``analyze_extremum``  某交易日四价「前低」回溯

- ``analyze_position``  区间四价极值位置百分比 + 升序排名：

  ``(结束日 − 最低) / (最高 − 最低) × 100%``



日线数据走系统现有 ``company.line.fetcher.fetch_kline``（前复权）。

"""



from __future__ import annotations



from company.analysis.line.extremum.position import (

    analyze_position,

    compute_position,

)

from company.analysis.line.extremum.service import (

    FACTOR_LABELS,

    FACTORS,

    analyze_extremum,

    compute_extremum,

)



__all__ = [

    "FACTOR_LABELS",

    "FACTORS",

    "analyze_extremum",

    "analyze_position",

    "compute_extremum",

    "compute_position",

]

