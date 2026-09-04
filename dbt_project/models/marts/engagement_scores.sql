with users as (
    select * from {{ ref('stg_users') }}
),

events as (
    select * from {{ ref('stg_events') }}
),

campaign as (
    select * from {{ ref('stg_campaign_sends') }}
),

reference_date as (
    select max(created_at) as as_of from events
),

app_opens as (
    select
        user_id,
        count(*)          as app_open_count,
        max(created_at)   as last_app_open_at
    from events
    where event_type = 'app_open'
    group by user_id
),

purchases as (
    select
        user_id,
        count(*)             as purchase_count,
        sum(revenue_amount)  as total_revenue
    from events
    where event_type = 'purchase'
    group by user_id
),

churn as (
    select distinct
        user_id,
        true as has_churned
    from events
    where event_type = 'churn'
),

campaign_engagement as (
    select
        user_id,
        count(*)                                          as campaign_sends_count,
        sum(case when was_opened then 1 else 0 end)        as campaign_opens_count
    from campaign
    group by user_id
),

joined as (
    select
        u.user_id,
        u.signup_date,
        u.country_code,
        coalesce(ao.app_open_count, 0)          as app_open_count,
        ao.last_app_open_at,
        coalesce(p.purchase_count, 0)           as purchase_count,
        coalesce(p.total_revenue, 0.0)          as total_revenue,
        coalesce(c.has_churned, false)          as has_churned,
        coalesce(ce.campaign_sends_count, 0)    as campaign_sends_count,
        coalesce(ce.campaign_opens_count, 0)    as campaign_opens_count,
        case
            when coalesce(ce.campaign_sends_count, 0) = 0 then 0.0
            else coalesce(ce.campaign_opens_count, 0)::double / ce.campaign_sends_count
        end                                                                     as campaign_open_rate,
        (select as_of from reference_date)                                      as reference_date,
        date_diff('day', ao.last_app_open_at, (select as_of from reference_date)) as days_since_last_open
    from users u
    left join app_opens ao          on u.user_id = ao.user_id
    left join purchases p           on u.user_id = p.user_id
    left join churn c               on u.user_id = c.user_id
    left join campaign_engagement ce on u.user_id = ce.user_id
),

scored as (
    select
        *,
        least(
            100.0,
            app_open_count * 5.0
            + purchase_count * 10.0
            + campaign_open_rate * 20.0
        ) as engagement_score
    from joined
)

select * from scored
