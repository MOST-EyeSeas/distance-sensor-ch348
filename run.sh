docker run --rm -it -v  $(pwd):/workspaces --net=host --privileged --volume=/dev:/dev --volume=/lib/modules:/lib/modules --volume=/sys:/sys distance-sensor /bin/bash
