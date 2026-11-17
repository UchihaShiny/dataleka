-- Gold dim: 1 dòng = 1 sản phẩm, kèm dòng sản phẩm và các thuộc tính đọc từ tag (brief: species, theme từ tag).
-- Cách chọn product_line (brief: productType + tiền tố SKU):
--   1. productType của Shopify nếu có (mẫu 7/11: cột này sạch: Long Sleeve, Phone Case, Ornament...)
--   2. không có thì tra tiền tố SKU trong seeds/product_lines.csv (chỉ có nghĩa với SKU chữ: MHL, RGO...;
--      SKU số như 100, 120 không mang nghĩa dòng sản phẩm)
--   3. vẫn không có thì '(không rõ)'
-- Tag của shop theo quy ước khoá:giá trị (khám phá ngày 10/11 trên mẫu 7/11):
--   species:bass, species:deer...      → loài (một sản phẩm có thể nhiều loài: species_all)
--   pc1:/orn1:/ls1:<chủ đề>            → theme theo bộ sưu tập (pc = phone case, orn = ornament, ls = long sleeve)
--   artist:miles, gender:men, water:fresh|salt
with prefix_count as (
    select product_id, sku_prefix, count(*) as variants
    from {{ ref('stg_variants') }}
    where sku_prefix is not null and sku_prefix != ''
    group by 1, 2
),

product_prefix as (
    -- Một sản phẩm có nhiều biến thể: lấy tiền tố xuất hiện nhiều nhất
    select product_id, array_agg(sku_prefix order by variants desc, sku_prefix limit 1)[offset(0)] as sku_prefix
    from prefix_count
    group by 1
),

tagged as (
    select
        product_id,
        array(
            select lower(trim(t)) from unnest(split(coalesce(tags, ''), ',')) as t with offset o
            where trim(t) != '' order by o
        ) as tag_list
    from {{ ref('stg_products') }}
),

attributes as (
    select
        product_id,
        (select split(t, ':')[safe_offset(1)] from unnest(tag_list) t with offset o
         where starts_with(t, 'species:') order by o limit 1)                         as species,
        array_to_string(array(select split(t, ':')[safe_offset(1)] from unnest(tag_list) t with offset o
         where starts_with(t, 'species:') order by o), ', ')                          as species_all,
        (select split(t, ':')[safe_offset(1)] from unnest(tag_list) t with offset o
         where regexp_contains(t, r'^[a-z]+1:') order by o limit 1)                   as theme,
        (select split(t, ':')[safe_offset(1)] from unnest(tag_list) t with offset o
         where starts_with(t, 'artist:') order by o limit 1)                          as artist,
        (select split(t, ':')[safe_offset(1)] from unnest(tag_list) t with offset o
         where starts_with(t, 'gender:') order by o limit 1)                          as gender,
        (select split(t, ':')[safe_offset(1)] from unnest(tag_list) t with offset o
         where starts_with(t, 'water:') order by o limit 1)                           as water
    from tagged
)

select
    p.product_id,
    p.title,
    p.handle,
    -- Link trang sản phẩm trên cửa hàng. Chỉ mở được khi sản phẩm ACTIVE (DRAFT, ARCHIVED sẽ báo 404).
    concat('{{ var("store_url") }}/products/', p.handle)                 as product_url,
    p.status = 'ACTIVE'                                                  as is_live,
    p.product_type,
    p.vendor,
    p.status,
    p.created_at,
    pp.sku_prefix,
    if(m.source = 'brief', m.product_subline, null)                      as brief_line,
    coalesce(nullif(p.product_type, ''), m.product_line, '(không rõ)')   as product_line,
    case
        when nullif(p.product_type, '') is not null then 'productType'
        when m.product_line is not null then 'tiền tố SKU'
        else 'không rõ'
    end                                                                  as product_line_source,
    -- Dòng con: chi tiết hơn productType (Long Sleeve = Performance Long Sleeve + Sun Hoodie + Women's Long Sleeve...).
    -- Tra tiền tố SKU; tiền tố lẻ hoặc SKU số thì dòng con = nhóm lớn.
    coalesce(m.product_subline,
             coalesce(nullif(p.product_type, ''), m.product_line, '(không rõ)'))   as product_subline,
    case
        when m.product_subline is not null then concat('tiền tố SKU (', m.source, ')')
        else 'bằng product_line'
    end                                                                  as product_subline_source,
    a.species,
    nullif(a.species_all, '')                                            as species_all,
    a.theme,
    a.artist,
    a.gender,
    a.water,
    p.tags                                                               as tags_raw
from {{ ref('stg_products') }} p
left join product_prefix pp on pp.product_id = p.product_id
left join {{ ref('product_lines') }} m on m.sku_prefix = pp.sku_prefix
left join attributes a on a.product_id = p.product_id
