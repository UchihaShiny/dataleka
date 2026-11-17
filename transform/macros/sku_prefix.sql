{#
  Ma dong san pham lay tu SKU.
  - Binh thuong: 3 chu dau, viet hoa (TPC239V-MAGSAFE-IPHONE16 -> TPC, ULS800K-L -> ULS).
  - SKU ban nhap bat dau bang DL + so (DL091K-ULS-5XL, DL002KH-FLS-XS, DL025V-BCT-BLACK-5XL):
    "DL.." chi la tien to cua ban nhap, ma dong that nam o phan thu 2 (ULS, FLS, BCT). Kiem 11/11.
  Dung chung cho stg_variants va stg_line_items de 2 noi luon ra cung mot ma.
#}
{% macro sku_prefix(column) -%}
case
    -- chi khi co phan thu 2 (co dau gach); khong co thi quay ve 3 chu dau
    when regexp_contains(upper({{ column }}), r'^DL\d[^-]*-[A-Z]') then upper(split({{ column }}, '-')[safe_offset(1)])
    else upper(substr({{ column }}, 1, 3))
end
{%- endmacro %}
