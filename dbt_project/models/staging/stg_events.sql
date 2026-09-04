with source as (
    select * from {{ source('raw', 'events') }}
),

renamed as (
    select
        event_id,
        user_id,
        event_type,
        cast(created_at as timestamp)   as created_at,
        revenue_amount
    from source
    where event_id is not null
      and user_id is not null
)

select * from renamed
