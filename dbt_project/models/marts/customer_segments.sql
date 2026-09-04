with scored as (
    select * from {{ ref('engagement_scores') }}
),

classified as (
    select
        user_id,
        signup_date,
        country_code,
        engagement_score,
        total_revenue,
        has_churned,
        days_since_last_open,
        case
            when has_churned
                or (days_since_last_open is not null and days_since_last_open > 30)
                then 'at_risk_churn'
            when date_diff('day', signup_date, reference_date) <= 14
                and app_open_count > 0
                then 'newly_activated'
            when total_revenue > 100
                then 'high_value'
            else 'standard'
        end as segment
    from scored
)

select * from classified
