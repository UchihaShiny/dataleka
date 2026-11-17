{#
  Mặc định dbt ghép tên dataset thành "<dataset mặc định>_<schema>", ví dụ silver_gold.
  DataE muốn đúng tên dataset đã tạo: silver, gold. Model khai +schema thì dùng đúng tên đó.
#}
{% macro generate_schema_name(custom_schema_name, node) -%}
    {%- if custom_schema_name is none -%}
        {{ target.schema }}
    {%- else -%}
        {{ custom_schema_name | trim }}
    {%- endif -%}
{%- endmacro %}
