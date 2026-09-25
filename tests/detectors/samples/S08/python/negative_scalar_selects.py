from django.db.models.expressions import RawSQL

child_count = RawSQL("SELECT COUNT(*) FROM ipam_prefix WHERE ipam_prefix.vrf_id = vrf.id", ())
exists_sql = "EXISTS (SELECT 1 FROM unnest(tags) AS t WHERE t = %s)"
path_sql = "SELECT path FROM tree_node WHERE id = %s"
