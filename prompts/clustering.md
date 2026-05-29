Compare each new pain with the existing clusters.

New pains ({pain_count} items, indexed from 0):
{pains_text}

Existing clusters:
{clusters_text}

For each new pain, return the cluster_id of the existing cluster if it is truly the same pain or very similar, or null if it is different.

Return only a valid JSON array with exactly {pain_count} elements, in the same order as the new pains:
[cluster_id_or_null, ...]

Example for 3 pains: [42, null, 17]

Group only pains that are truly the same or very similar. Do not group pains merely because they are related.
