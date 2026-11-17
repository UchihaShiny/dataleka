{#
  NGÀY ĐÃ TRỌN của kho (giờ Phoenix): mọi mart dùng chung để không chỗ nào tính lẫn ngày đang dở.
  - Có var complete_through (pipelines/dbt.py tự truyền: ngày Phoenix lúc BẮT ĐẦU kéo Shopify − 1, đọc từ
    data/last_load.json): dùng nó, nhưng không vượt ngày mới nhất có đơn.
  - Không có var (máy chưa nạp lần nào): đoán như cũ = ngày mới nhất có đơn − 1.
  Vì sao (16/11): nạp lúc 00:07 Phoenix ngày 16, ngày 16 chưa có đơn nên "mới nhất − 1" ra 14/11 dù 15/11 đã đủ.
  Câu SQL chạy trên console (checks/sql/*.sql) không gọi được macro: đọc gold.load_status.complete_through.
#}
{% macro complete_through() -%}
{%- set v = var('complete_through', none) -%}
{%- if v -%}
{%- if not modules.re.match('^[0-9]{4}-[0-9]{2}-[0-9]{2}$', v | string) -%}
{{ exceptions.raise_compiler_error("complete_through phải dạng YYYY-MM-DD, nhận: " ~ v) }}
{%- endif -%}
least(date '{{ v }}', (select max(order_date) from {{ ref('fct_orders') }}))
{%- else -%}
(select date_sub(max(order_date), interval 1 day) from {{ ref('fct_orders') }})
{%- endif -%}
{%- endmacro %}
