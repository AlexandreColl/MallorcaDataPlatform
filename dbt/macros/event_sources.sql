{#- Sources whose rows are irregular events (frequency: event in connector.yaml), not time series.
    Time-series models (daily aggregates, locations) leave them out; events have their own facts. -#}
{% macro event_sources() -%}
    ({%- for source in var('event_sources') -%}'{{ source }}'{%- if not loop.last %}, {% endif -%}{%- endfor -%})
{%- endmacro %}
