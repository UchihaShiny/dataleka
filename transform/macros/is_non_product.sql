{#
  Dòng KHÔNG PHẢI SẢN PHẨM, nhận theo tên: Tip, UpCart / Shipping Protection, Gift Card.
  "gift card" phải là cả cụm từ (\b): bản đầu 12/11 khớp nhầm "Seed Gift Cardinal Pair" (ornament thật).
  Dùng chung cho mart_product_abc, mart_product_xyz để mọi nơi loại cùng một tập. Chờ anh Quang chốt danh sách.
  Câu SQL chạy trên console (checks/sql/*.sql) không gọi được macro: chép đúng biểu thức dưới đây.
#}
{% macro is_non_product(column) -%}
regexp_contains(lower(coalesce({{ column }}, '')), r'^tip$|upcart|shipping protection|\bgift card\b')
{%- endmacro %}
