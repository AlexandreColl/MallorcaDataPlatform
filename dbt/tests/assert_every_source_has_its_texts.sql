-- Every source of the catalogue has its texts in each language of dim_source_texts: a source added to dim_sources
-- without them would show its Spanish label in the Catalan and English web.
select s.source, l.language
from {{ ref('dim_sources') }} as s
cross join (select distinct language from {{ ref('dim_source_texts') }}) as l
left join {{ ref('dim_source_texts') }} as t on s.source = t.source and l.language = t.language
where t.source is null
