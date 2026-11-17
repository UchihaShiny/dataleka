-- Gold: lịch sự kiện (seed events, nằm ở silver) đưa lên gold để MCP đọc được (khoá MCP chỉ đọc gold).
-- 1 dòng = 1 ngày có sự kiện. kind: le (ngày lễ) | mua_sam (BFCM) | tang_qua (Valentine, Mother's Day...) | sale | campaign.
select date, event, kind, note
from {{ ref('events') }}
