DROP TABLE IF EXISTS feed_entries;
DROP TABLE IF EXISTS feed_meta;

CREATE TABLE feed_meta (
    id SERIAL PRIMARY KEY,
    feed_url TEXT NOT NULL,
    feed_title TEXT,
    feed_subtitle TEXT,
    feed_updated TIMESTAMP WITH TIME ZONE,
    feed_id_in_atom TEXT,
    rights TEXT,
    category TEXT,
    frequency_type TEXT CHECK (frequency_type IN ('高頻度', '長期')),
    last_fetched TIMESTAMP WITH TIME ZONE
);

CREATE TABLE feed_entries (
    id SERIAL PRIMARY KEY,
    feed_id INTEGER REFERENCES feed_meta(id),
    entry_id_in_atom TEXT,
    entry_title TEXT,
    entry_updated TIMESTAMP WITH TIME ZONE,
    entry_author TEXT,
    entry_link TEXT,
    entry_content TEXT,
    inserted_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
