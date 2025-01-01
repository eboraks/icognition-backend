SELECT id, text, source_type, source_id, 1.0 AS cosine_similarity 
    FROM public.embedding
    WHERE search_vector @@ plainto_tsquery('english', 'Jim Cramer NEP')
    AND source_type IN ('document')
    GROUP BY 1, 2, 3, 4