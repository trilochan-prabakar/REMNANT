vcl 4.1;

backend default {
    .host = "origin";
    .port = "8000";
    .connect_timeout = 2s;
    .first_byte_timeout = 5s;
    .between_bytes_timeout = 2s;
}

acl purge {
    "0.0.0.0"/0;
}

sub vcl_recv {
    # This fixture is bound to localhost by Compose; PURGE is enabled only here.
    if (req.method == "PURGE") {
        if (client.ip !~ purge) {
            return (synth(405, "PURGE not allowed"));
        }
        return (purge);
    }

    # Test-fixture control operations must never be cached.
    if (req.url ~ "^/__remnant__/control/") {
        return (pass);
    }

    if (req.method != "GET" && req.method != "HEAD") {
        return (pass);
    }

    return (hash);
}

sub vcl_hash {
    hash_data(req.url.path);
    if (req.http.host) {
        hash_data(req.http.host);
    }
    # Deliberately omit the query string. The fixture demonstrates a broken
    # identity cache key: ?principal=alice and ?principal=bob collide.
    return (lookup);
}

sub vcl_backend_response {
    set beresp.ttl = 120s;
    set beresp.grace = 0s;
}

sub vcl_deliver {
    if (obj.hits > 0) {
        set resp.http.X-Cache-Status = "HIT";
    } else {
        set resp.http.X-Cache-Status = "MISS";
    }
    unset resp.http.Server;
}
