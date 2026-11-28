{#- Season of a month for the unemployment marts: `summer` June to September (the high tourist season), `winter`
    November to February (most hotels closed), null for the shoulder months. -#}
{% macro unemployment_season(month) -%}
case
    when extract(month from {{ month }}) between 6 and 9 then 'summer'
    when extract(month from {{ month }}) in (11, 12, 1, 2) then 'winter'
end
{%- endmacro %}
