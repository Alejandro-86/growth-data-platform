with source as (
    select * from {{ source('raw', 'campaign_sends') }}
),

renamed as (
    select
        send_id,
        user_id,
        campaign_id,
        channel,
        cast(sent_at as timestamp)      as sent_at,
        cast(opened_at as timestamp)    as opened_at,
        opened_at is not null           as was_opened
    from source
    where send_id is not null
      and user_id is not null
)

select * from renamed
