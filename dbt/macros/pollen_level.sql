{#- The pollen level of a daily mean in grains/m3, from the thresholds in `vars.pollen_levels` (REA). -#}
{% macro pollen_level(column, pollen) -%}
{%- set levels = var('pollen_levels')[pollen] -%}
case
    when {{ column }} is null then null
    when {{ column }} >= {{ levels['high'] }} then 'high'
    when {{ column }} >= {{ levels['moderate'] }} then 'moderate'
    when {{ column }} >= {{ levels['low'] }} then 'low'
    else 'none'
end
{%- endmacro %}
