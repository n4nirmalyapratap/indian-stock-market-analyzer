#!/bin/sh

# Generate env.js containing all environment variables starting with VITE_
generate_env_js() {
  local target_file=$1
  echo "window.__ENV__ = {" > "$target_file"
  
  # Safeguard against grep returning 1 if no matching vars are found
  vars=$(env | grep ^VITE_ || true)
  if [ -n "$vars" ]; then
    echo "$vars" | while read -r line; do
      key=$(echo "$line" | cut -d= -f1)
      val=$(echo "$line" | cut -d= -f2-)
      # Escape double quotes and backslashes for JS string safety
      val_escaped=$(echo "$val" | sed 's/\\/\\\\/g; s/"/\\"/g')
      echo "  \"$key\": \"$val_escaped\"," >> "$target_file"
    done
  fi
  echo "};" >> "$target_file"
}

# Write env.js to the user app and admin dashboard directories
generate_env_js "/usr/share/nginx/html/env.js"
generate_env_js "/usr/share/nginx/admin/env.js"

# Execute the main container command (CMD)
exec "$@"
