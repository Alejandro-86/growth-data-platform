with source as (
    select * from {{ source('raw', 'users') }}
),

renamed as (
    select
        user_id,
        lower(email)                          as email,
        cast(created_at as timestamp)         as created_at,
        cast(created_at as date)              as signup_date,
        coalesce(country_code, 'unknown')     as country_code
    from source
    where user_id is not null
)

select * from renamed
