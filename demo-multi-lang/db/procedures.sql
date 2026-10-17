-- User authentication procedures

CREATE OR REPLACE FUNCTION authenticate_user(
    p_username VARCHAR,
    p_password VARCHAR
)
RETURNS BOOLEAN AS $$
DECLARE
    v_stored_password VARCHAR;
    v_is_valid BOOLEAN;
BEGIN
    -- Get stored password
    SELECT password INTO v_stored_password
    FROM users
    WHERE username = p_username;
    
    -- Validate password
    v_is_valid := validate_password(p_password, v_stored_password);
    
    -- Log authentication attempt
    CALL log_auth_attempt(p_username, v_is_valid);
    
    RETURN v_is_valid;
END;
$$ LANGUAGE plpgsql;


CREATE OR REPLACE FUNCTION validate_password(
    p_plain_password VARCHAR,
    p_hashed_password VARCHAR
)
RETURNS BOOLEAN AS $$
BEGIN
    -- Simplified: in real app use bcrypt or similar
    RETURN p_plain_password = p_hashed_password;
END;
$$ LANGUAGE plpgsql;


CREATE OR REPLACE PROCEDURE log_auth_attempt(
    p_username VARCHAR,
    p_success BOOLEAN
)
AS $$
BEGIN
    INSERT INTO auth_logs (username, success, timestamp)
    VALUES (p_username, p_success, NOW());
END;
$$ LANGUAGE plpgsql;


CREATE OR REPLACE FUNCTION get_user_profile(p_user_id INT)
RETURNS TABLE(id INT, name VARCHAR, email VARCHAR) AS $$
BEGIN
    RETURN QUERY
    SELECT u.id, u.name, u.email
    FROM users u
    WHERE u.id = p_user_id;
END;
$$ LANGUAGE plpgsql;
