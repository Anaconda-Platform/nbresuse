import os
import json
from os.path import join
from traitlets import Float, Int, default
from traitlets.config import Configurable
from notebook.utils import url_path_join
from notebook.base.handlers import IPythonHandler
from tornado import web

class CGroup(object):
    def __init__(self):
        # cgroups in AE5 are configured globally for the container
        # rather than per user
        self.path = '/sys/fs/cgroup/'


    def _load_memory_data(self):
        '''Load current memory usage and limit information
        this must be called frequently to get up-to-date information.
        '''
        with open(join(self.path, 'memory', 'memory.stat')) as f:
            lines = f.readlines()

        return {i.split()[0]:int(i.split()[1]) for i in lines}


    @property
    def mem_limit(self):
        '''CGroups memory limit in bytes'''

        # don't forget to get the current values
        m = self._load_memory_data()
        return m['hierarchical_memory_limit']


    @property
    def mem_usage(self):
        '''Current total memory usage in bytes'''

        # don't forget to get the current values
        m = self._load_memory_data()
        return m['total_rss']


class MetricsHandler(IPythonHandler):
    @web.authenticated
    def get(self):
        """
        Calculate and return current resource usage metrics
        """
        config = self.settings['nbresuse_display_config']

        cgroup = CGroup()
        rss = cgroup.mem_usage

        limits = {}

        limits['memory'] = {
            'rss': cgroup.mem_limit
        }
        if config.mem_warning_threshold != 0:
            limits['memory']['warn'] = (cgroup.mem_limit - rss) < (cgroup.mem_limit * config.mem_warning_threshold)
        metrics = {
            'rss': rss,
            'limits': limits,
        }
        self.write(json.dumps(metrics))


def _jupyter_server_extension_paths():
    """
    Set up the server extension for collecting metrics
    """
    return [{
        'module': 'nbresuse',
    }]

def _jupyter_nbextension_paths():
    """
    Set up the notebook extension for displaying metrics
    """
    return [{
        "section": "notebook",
        "dest": "nbresuse",
        "src": "static",
        "require": "nbresuse/main"
    }]

class ResourceUseDisplay(Configurable):
    """
    Holds server-side configuration for nbresuse
    """

    mem_warning_threshold = Float(
        0.2,
        help="""
        Warn user with flashing lights when memory usage is within this fraction
        memory limit.

        For example, if memory limit is 128MB, `mem_warning_threshold` is 0.1,
        we will start warning the user when they use (128 - (128 * 0.1)) MB.

        Set to 0 to disable warning.
        """,
        config=True
    )

    mem_limit = Int(
        0,
        config=True,
        help="""
        Memory limit to display to the user, in bytes.

        Note that this does not actually limit the user's memory usage!

        Defaults to reading from the `MEM_LIMIT` environment variable. If
        set to 0, no memory limit is displayed.
        """
    )

    @default('mem_limit')
    def _mem_limit_default(self):
        return int(os.environ.get('MEM_LIMIT', 0))

def load_jupyter_server_extension(nbapp):
    """
    Called during notebook start
    """
    resuseconfig = ResourceUseDisplay(parent=nbapp)
    nbapp.web_app.settings['nbresuse_display_config'] = resuseconfig
    route_pattern = url_path_join(nbapp.web_app.settings['base_url'], '/metrics')
    nbapp.web_app.add_handlers('.*', [(route_pattern, MetricsHandler)])
