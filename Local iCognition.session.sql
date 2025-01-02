select e.name, e.id, e.description
from entity e 
where e.name like 'BBC'
group by e.name, e.id