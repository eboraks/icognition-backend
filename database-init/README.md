# Rebuild the containers
docker-compose up --build --force-recreate -d

Options:
    -d, --detach        Detached mode: Run containers in the background,
                        print new container names. Incompatible with
                        --abort-on-container-exit.
    --no-deps           Don't start linked services.
    --force-recreate    Recreate containers even if their configuration
                        and image haven't changed.
    --build             Build images before starting containers.


# Find postgres IP
1. Find container ID ->  docker ps
2. Find IP -> docker inspect 87c13e1f865a | grep IPAddress


# Knowledge Graph Queries

## Schema: `entity_relationships` table (added Phase 5)

```sql
CREATE TABLE entity_relationships (
    id                 SERIAL PRIMARY KEY,
    from_entity_id     INTEGER REFERENCES entities(id),
    to_entity_id       INTEGER REFERENCES entities(id),
    relationship_type  VARCHAR(100),
    source_document_id INTEGER REFERENCES document(id),
    created_at         TIMESTAMPTZ DEFAULT now(),
    UNIQUE (from_entity_id, to_entity_id, relationship_type, source_document_id)
);
```

## All relationships with entity names and source document

```sql
SELECT
    e1.name            AS from_entity,
    r.relationship_type,
    e2.name            AS to_entity,
    d.title            AS source_document
FROM entity_relationships r
JOIN entities e1 ON e1.id = r.from_entity_id
JOIN entities e2 ON e2.id = r.to_entity_id
LEFT JOIN document d ON d.id = r.source_document_id
ORDER BY r.created_at DESC
LIMIT 50;
```

## Count relationships per document

```sql
SELECT d.title, COUNT(*) AS relationship_count
FROM entity_relationships r
JOIN document d ON d.id = r.source_document_id
GROUP BY d.title
ORDER BY relationship_count DESC;
```

## All entities and how many documents they appear in

```sql
SELECT e.name, e.type, COUNT(ed.document_id) AS doc_count
FROM entities e
JOIN entity_documents ed ON ed.entity_id = e.id
GROUP BY e.id, e.name, e.type
ORDER BY doc_count DESC;
```

## Relationships for a specific entity (replace 'OpenAI' with any name)

```sql
SELECT
    e1.name            AS from_entity,
    r.relationship_type,
    e2.name            AS to_entity
FROM entity_relationships r
JOIN entities e1 ON e1.id = r.from_entity_id
JOIN entities e2 ON e2.id = r.to_entity_id
WHERE e1.name ILIKE '%OpenAI%'
   OR e2.name ILIKE '%OpenAI%';
```

## Note
The `entity_relationships` table is populated only for documents processed **after** Phase 5 was deployed.
To populate relationships for existing documents, re-trigger entity extraction via the system endpoint.
