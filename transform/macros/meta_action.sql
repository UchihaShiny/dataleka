{#
  Lay so cua 1 action_type trong cot JSON actions/action_values cua Meta.
  Mot su kien nam duoi nhieu ten (purchase, omni_purchase, offsite_conversion.fb_pixel_purchase...):
  chi lay DUNG 1 ten, khong cong don (xem docs/meta-schema.md).
#}
{% macro meta_action(column, action_type) -%}
coalesce((
    select sum(cast(json_value(a, '$.value') as numeric))
    from unnest(json_query_array({{ column }})) as a
    where json_value(a, '$.action_type') = '{{ action_type }}'
), 0)
{%- endmacro %}
