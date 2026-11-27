{#- The day of the year of a date on a 366-day calendar: 29 February is always day 60 and 1 March day 61, so the
    same calendar day has the same number in leap and common years (climatologies per day of the year). -#}
{% macro day_of_year_366(day) -%}
extract(doy from make_date(2000, extract(month from {{ day }})::integer, extract(day from {{ day }})::integer))::integer
{%- endmacro %}
