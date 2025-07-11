#!/usr/bin/env python
# -*- coding: utf-8 -*-

# Copyright: (c) 2022, Marc Crébassa <aalaesar@gmail.com>
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:

# * Redistributions of source code must retain the above copyright notice, this
#   list of conditions and the following disclaimer.

# * Redistributions in binary form must reproduce the above copyright notice,
#   this list of conditions and the following disclaimer in the documentation
#   and/or other materials provided with the distribution.

# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
# DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE
# FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
# DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
# SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
# CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
# OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
# OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

import os
from ansible_collections.nextcloud.admin.plugins.module_utils.exceptions import (
    OccExceptions,
    OccAuthenticationException,
    OccFileNotFoundException,
    OccNoCommandsDefined,
    OccNotEnoughArguments,
    OccOptionRequiresValue,
    OccOptionNotDefined,
)
from shlex import shlex
import copy


NC_TOOLS_ARGS_SPEC = dict(
    nextcloud_path=dict(
        type="str", required=True, aliases=["path", "nc_path", "nc_dir"]
    ),
    php_runtime=dict(type="str", required=False, default="php", aliases=["php"]),
)


def extend_nc_tools_args_spec(some_module_spec):
    arg_spec = copy.deepcopy(NC_TOOLS_ARGS_SPEC)
    arg_spec.update(some_module_spec)
    return arg_spec


def convert_string(command: str) -> list:
    command_lex = shlex(command, posix=False)
    command_lex.whitespace_split = True
    command_lex.commenters = ""
    command_lex.escape = ""
    command_lex.quotes = "\"'"
    return [token if " " in token else token.strip("\"'") for token in command_lex]


def run_occ(
    module,
    command,
):
    cli_full_path = module.params.get("nextcloud_path") + "/occ"
    php_exec = module.params.get("php_runtime")
    try:
        cli_stats = os.stat(cli_full_path)
    except FileNotFoundError:
        raise OccFileNotFoundException()

    if os.getuid() != cli_stats.st_uid:
        module.debug(f"DEBUG: Switching user to id {cli_stats.st_uid}.")
        try:
            os.setgid(cli_stats.st_gid)
            os.setuid(cli_stats.st_uid)
        except PermissionError:
            raise OccAuthenticationException(
                msg="Insufficient permissions to switch to user id {}.".format(
                    cli_stats.st_uid
                )
            )

    if isinstance(command, list):
        full_command = [cli_full_path] + ["--no-ansi"] + command
    elif isinstance(command, str):
        full_command = [cli_full_path] + ["--no-ansi"] + convert_string(command)

    module.debug(f"DEBUG: Running command '{[php_exec] + full_command}'.")
    result = dict(
        zip(("rc", "stdout", "stderr"), module.run_command([php_exec] + full_command))
    )
    if "is in maintenance mode" in result["stderr"]:
        module.warn(" ".join(result["stderr"].splitlines()[0:1]))
        maintenanceMode = True
    else:
        maintenanceMode = False

    if "is not installed" in result["stderr"]:
        module.warn(result["stderr"].splitlines()[0])

    output = result["stderr"] or result["stdout"]
    if result["rc"] != 0 and output:
        error_msg = convert_string(output.strip().splitlines()[0])
        if all(x in error_msg for x in ["Command", "is", "not", "defined."]):
            raise OccNoCommandsDefined(full_command, **result)
        elif all(x in error_msg for x in ["Not", "enough", "arguments"]):
            raise OccNotEnoughArguments(full_command, **result)
        elif all(x in error_msg for x in ["option", "does", "not", "exist."]):
            raise OccOptionNotDefined(full_command, **result)
        elif all(x in error_msg for x in ["option", "requires", "value."]):
            raise OccOptionRequiresValue(full_command, **result)
        else:
            raise OccExceptions(full_command, **result)
    elif result["rc"] != 0:
        raise OccExceptions(full_command, **result)

    return result["rc"], result["stdout"], result["stderr"], maintenanceMode
