# Schema Meta Ads: khám phá trên 1 ngày mẫu (7/11/2026)

Nguồn: `python checks/explore_meta.py` (42 lần gọi, mức dùng cao nhất 18%) rồi `python checks/profile_sample.py meta`.
Mẫu JSON ở `data/explore/meta/` (trên máy, gitignore), profile từng trường ở `data/explore/meta/profile.md`.
Tài khoản có spend: 1 (`918678220936371`), USD, America/Phoenix.

## Sơ đồ

```text
ad account (1)
 └─ campaign (29)          objective, budget (15/29 đặt ngân sách ở campaign), bid_strategy
     └─ adset (154)        optimization_goal, targeting, attribution_spec, budget (139/154)
         └─ ad (215)       status, tracking_specs, creative{id}
             └─ creative   1 ad : 1 creative (215 ad → 215 creative)
insights (date × ad)      số liệu: spend, impressions, clicks, actions[], action_values[]
```

- Một adset có 1–6 ad (112/154 adset chỉ có 1 ad). Một campaign có 1–32 adset (20/29 campaign chỉ có 1 adset).
- Insights đã mang sẵn `campaign_id`, `adset_id`, `ad_id`, nên muốn có tên và cấu hình thì nối về campaign, adset, ad, creative theo id.

## Từng bảng

| Bảng | Grain | Khoá | Khoá nối | Trường đáng lấy | Ghi chú |
|---|---|---|---|---|---|
| `campaign` | 1 campaign | `id` | `account_id` | `name`, `objective`, `status`/`effective_status`, `daily_budget`, `bid_strategy`, `buying_type`, `smart_promotion_type`, `start_time`, `created_time` | 29/29 là `OUTCOME_SALES`. `daily_budget` tính bằng xu (cent). |
| `adset` | 1 adset | `id` | `campaign_id` | `name`, `optimization_goal`, `billing_event`, `daily_budget`, `attribution_spec`, `promoted_object`, `targeting` (JSON), `learning_stage_info`, `destination_type` | 154/154 tối ưu `OFFSITE_CONVERSIONS`, sự kiện `PURCHASE`, attribution 7 ngày click + 1 ngày view. |
| `ad` | 1 ad | `id` | `adset_id`, `campaign_id`, `creative.id` | `name`, `effective_status`, `created_time`, `tracking_specs` | Đang có ở `raw.meta_ads` (thiếu `tracking_specs`). |
| `adcreative` | 1 creative | `id` | qua `ad.creative.id` | `title`, `body`, `call_to_action_type`, `object_type`, `url_tags`, link trong `object_story_spec`, `asset_feed_spec`, `product_set_id`, `thumbnail_url` | Profile ra 157 đường dẫn trường vì JSON lồng sâu. 5/20 mẫu là dynamic creative (`asset_feed_spec`), 4/20 là quảng cáo catalog (`product_set_id`). |
| `insights` | ngày × ad | `date_start`, `ad_id` | `ad_id`, `adset_id`, `campaign_id` | `spend`, `impressions`, `reach`, `frequency`, `clicks`, `inline_link_clicks`, `outbound_clicks`, `actions`, `action_values`, `purchase_roas`, `video_*` | Đang lấy 14 trường; bộ rộng 39 trường chạy được hết, không trường nào bị từ chối. |
| `insights × vị trí` | ngày × campaign × `publisher_platform` × `platform_position` | | `campaign_id` | `spend`, `impressions`, `clicks`, `actions` | Facebook 2.757 / Instagram 667 / Threads 7 USD trong 3.436 USD. Chỉ lấy nếu cần phân tích vị trí. |

## Kiểm quan hệ trên mẫu (tất cả đạt)

- 215/215 `ad_id` của insights có trong bảng ad; 215/215 adset của ad có trong bảng adset; 154/154 campaign của adset có trong bảng campaign.
- `adset_id` trong insights trùng với `ad.adset_id` ở 215/215 dòng.
- `creative.id` của ad trùng với cache `raw.meta_ads` ở 215/215 ad.
- **Spend qua 3 lần gọi độc lập:** insights cấp ad của pipeline 3.435,71, cấp ad với bộ trường rộng 3.435,54, cấp campaign × vị trí 3.435,71 USD. Lệch tối đa 0,17 USD, do Meta còn chỉnh số ngày gần.

## Bẫy

1. **Một lượt mua nằm dưới 8 tên `action_type`.** Ngày 7/11: `purchase`, `omni_purchase`, `offsite_conversion.fb_pixel_purchase`, `onsite_web_app_purchase`, `web_in_store_purchase`, `offsite_purchase_add_20_s_calls`... đều là 116. Cộng hết là đếm gấp nhiều lần. Chỉ lấy `purchase`. Các bước khác trong phễu cũng vậy (`view_content`, `add_to_cart`, `initiate_checkout`).
2. **Meta tự nhận 116 trên 128 đơn Shopify của ngày (91%), giá trị 5.800,88 trên 6.417,66.** Klaviyo tự nhận thêm 2 đơn. Vì vậy MER, CPO tính bằng đơn Shopify, không cộng purchase của các nguồn lại.
3. **Xin thêm trường thì Meta trả cả ad không chạy.** Bộ trường rộng (có ranking, objective) trả 2.654 dòng cho 1 ngày, trong khi chỉ 210 ad có impression. Phải lọc `impressions > 0`.
4. **`effective_status` là trạng thái hôm nay, không phải của ngày đó.** 87/215 ad có spend ngày 7/11 nay đã `ADSET_PAUSED`/`CAMPAIGN_PAUSED`. Lấy trạng thái lịch sử thì phải chụp mỗi ngày.
5. **`reach`, `frequency`, `unique_*` không cộng được qua ngày hay qua ad.**
6. **Ngân sách tính bằng xu**, và đặt ở campaign (CBO) hoặc adset, không đặt ở cả hai.
7. **`?metadata=1` không còn trả gì ở v27**, nên danh sách trường lấy theo tài liệu Marketing API. **Edge `adcreatives` không lọc được theo id** (`'id' with operation 'in' is not supported`): lần sau lấy creative lồng trong ad (`ads?fields=creative{...}`), 5 lần gọi cho cả 215 creative.

## Cơ hội nối với Shopify

- `url_tags` của creative: `utm_source=facebook-ad&utm_medium={{campaign.name}}&utm_campaign={{adset.name}}&utm_content={{ad.name}}_{{ad.id}}`. Nếu đơn Shopify giữ được UTM của lượt ghé (`customerJourneySummary`, chưa khám phá vì là object), thì nối được **đơn → ad** mà không cần tin số purchase của Meta.
- Link trong creative trỏ thẳng tới sản phẩm (`thedeerly.com/products/tpc260k`, `?featured=rgo399k`). Handle/SKU có tiền tố trùng với SKU Shopify (TPC, RGO, ULS...), nên nối được **ad → dòng sản phẩm**.

## Đề xuất cho raw (chờ anh Quang duyệt)

- Thêm `raw.meta_campaigns`, `raw.meta_adsets`, `raw.meta_creatives` (chụp lại mỗi ngày, ghi đè; nhỏ: vài trăm dòng).
- Insights thêm: `frequency`, `outbound_clicks`, `purchase_roas`, `video_play_actions`, `video_p25…p100_watched_actions`, `video_thruplay_watched_actions`, `quality_ranking`, `engagement_rate_ranking`, `conversion_rate_ranking`, `attribution_setting`, `objective`, `optimization_goal`. Giữ `level=ad`, `time_increment=1`, lọc `impressions > 0`.
- Bỏ: breakdown theo vị trí (để sau, khi có câu hỏi cụ thể), `cpc`/`cpm`/`ctr` (tính lại được từ spend, clicks, impressions).
- Rồi mới gom lịch sử về 11/2024.
