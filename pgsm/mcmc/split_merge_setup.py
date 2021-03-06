'''
Created on 9 Jan 2017

@author: Andrew Roth
'''
from __future__ import division

import numpy as np

from pgsm.math_utils import discrete_rvs, exp_normalize, log_normalize, log_sum_exp
from pgsm.utils import relabel_clustering


class SplitMergeSetupKernel(object):
    '''
    Base class for kernel to setup a split merge move.
    '''

    def __init__(self, data, dist, partition_prior, num_adaptation_iters=float('inf')):
        self.data = data

        self.dist = dist

        self.partition_prior = partition_prior

        self.num_adaptation_iters = num_adaptation_iters

        self.iter = 0

        self.num_data_points = len(data)

    def setup_split_merge(self, clustering, num_anchors):
        self.iter += 1

        clustering = np.array(clustering, dtype=np.int)

        if self._can_update(clustering):
            self.update(clustering)

        num_data_points = len(clustering)

        num_anchors = min(num_anchors, num_data_points)

        anchors = self._propose_anchors(num_anchors)

        anchor_clusters = set([clustering[a] for a in anchors])

        sigma = set()

        for c in anchor_clusters:
            sigma.update(np.argwhere(clustering == c).flatten())

        sigma = list(sigma)

        for x in anchors:
            sigma.remove(x)

        np.random.shuffle(sigma)

        return anchors, list(anchors) + sigma

    def update(self, clustering):
        pass

    def _can_update(self, clustering):
        raise NotImplementedError()

    def _propose_anchors(self, num_anchors):
        raise NotImplementedError()


class UniformSplitMergeSetupKernel(SplitMergeSetupKernel):
    '''
    Setup a split merge move by selecting anchors uniformly.
    '''

    def _can_update(self, clustering):
        return False

    def _propose_anchors(self, num_anchors):
        return np.random.choice(np.arange(self.num_data_points), replace=False, size=num_anchors)


class ThresholdInformedSplitMergeSetupKernel(SplitMergeSetupKernel):

    def __init__(self, data, dist, partition_prior, num_adaptation_iters=float('inf'), threshold=0.01):
        SplitMergeSetupKernel.__init__(self, data, dist, partition_prior, num_adaptation_iters=num_adaptation_iters)

        self.max_clusters_seen = 0

        self.threshold = threshold

    def update(self, clustering):
        self.cluster_params = {}

        self.clusters_to_data = {}

        self.data_to_clusters = {}

        self.clustering = relabel_clustering(clustering)

        for c in np.unique(clustering):
            cluster_data = self.data[clustering == c]

            self.cluster_params[c] = self.dist.create_params()

            for data_point in cluster_data:
                self.cluster_params[c].increment(data_point)

            self.clusters_to_data[c] = np.where(clustering == c)[0].flatten()

    def _can_update(self, clustering):
        num_clusters = len(np.unique(clustering))

        if (num_clusters > self.max_clusters_seen) and (self.iter <= self.num_adaptation_iters):
            can_update = True

            self.max_clusters_seen = num_clusters

        else:
            can_update = False

        return can_update

    def _propose_anchors(self, num_anchors):
        if num_anchors != 2:
            raise Exception('ThresholdInformedSplitMergeSetupKernel only works for 2 anchors')

        anchor_1 = np.random.randint(0, self.num_data_points)

        if anchor_1 not in self.data_to_clusters:
            self._set_data_to_clusters(anchor_1)

        if len(self.data_to_clusters[anchor_1]) == 0:
            return np.random.choice(np.arange(self.num_data_points), replace=False, size=2)

        cluster = np.random.choice(self.data_to_clusters[anchor_1])

        cluster_members = set(self.clusters_to_data[cluster])

        cluster_members.discard(anchor_1)

        if len(cluster_members) == 0:
            return np.random.choice(np.arange(self.num_data_points), replace=False, size=2)

        anchor_2 = np.random.choice(list(cluster_members))

        return int(anchor_1), int(anchor_2)

    def _set_data_to_clusters(self, data_idx):
        data_point = self.data[data_idx]

        num_clusters = len(self.cluster_params)

        log_p = np.zeros(num_clusters)

        cluster = self.clustering[data_idx]

        for c, block_params in self.cluster_params.items():
            if c == cluster:
                block_params.decrement(data_point)

            if block_params.N == 0:
                log_p[c] = float('-inf')

            else:
                log_p[c] = self.partition_prior.log_tau_2(block_params.N)

                log_p[c] += self.dist.log_predictive_likelihood(data_point, block_params)

            if c == cluster:
                block_params.increment(data_point)

        log_p = log_normalize(log_p)

        self.data_to_clusters[data_idx] = []

        for c, log_p_c in enumerate(log_p):
            if log_p_c >= np.log(self.threshold):
                self.data_to_clusters[data_idx].append(c)


class CRPInformedSplitMergeSetupKernel(SplitMergeSetupKernel):

    def __init__(self, data, dist, partition_prior, num_adaptation_iters=float('inf')):
        SplitMergeSetupKernel.__init__(self, data, dist, partition_prior, num_adaptation_iters=num_adaptation_iters)

        self.max_clusters_seen = 0

    def update(self, clustering):
        self.cluster_params = {}

        self.clusters_to_data = {}

        self.data_to_clusters = {}

        self.clustering = relabel_clustering(clustering)

        for c in np.unique(clustering):
            cluster_data = self.data[clustering == c]

            self.cluster_params[c] = self.dist.create_params()

            for data_point in cluster_data:
                self.cluster_params[c].increment(data_point)

            self.clusters_to_data[c] = np.where(clustering == c)[0].flatten()

    def _can_update(self, clustering):
        num_clusters = len(np.unique(clustering))

        if (num_clusters > self.max_clusters_seen) and (self.iter <= self.num_adaptation_iters):
            can_update = True

            self.max_clusters_seen = num_clusters

        else:
            can_update = False

        return can_update

    def _propose_anchors(self, num_anchors):
        if num_anchors != 2:
            raise Exception('CRPInformedSplitMergeSetupKernel only works for 2 anchors')

        anchor_1 = np.random.randint(0, self.num_data_points)

        if anchor_1 not in self.data_to_clusters:
            self._set_data_to_clusters(anchor_1)

        cluster = np.random.choice(self.data_to_clusters[anchor_1].keys(), p=self.data_to_clusters[anchor_1].values())

        cluster_members = set(self.clusters_to_data[cluster])

        cluster_members.discard(anchor_1)

        anchor_2 = np.random.choice(list(cluster_members))

        return int(anchor_1), int(anchor_2)

    def _set_data_to_clusters(self, data_idx):
        data_point = self.data[data_idx]

        num_clusters = len(self.cluster_params)

        log_p = np.zeros(num_clusters)

        cluster = self.clustering[data_idx]

        for c, block_params in self.cluster_params.items():
            if c == cluster:
                continue

            else:
                log_p[c] = self.partition_prior.log_tau_2(block_params.N)

                log_p[c] += self.dist.log_predictive_likelihood(data_point, block_params)

        if self.cluster_params[cluster].N == 1:
            log_p[cluster] = float('-inf')

        else:
            log_p[cluster] = log_sum_exp(log_p)

            if num_clusters > 1:
                log_p[cluster] -= np.log(num_clusters - 1)

        p, _ = exp_normalize(log_p)

        self.data_to_clusters[data_idx] = dict(zip(self.cluster_params.keys(), p))


class ClusterInformedSplitMergeSetupKernel(SplitMergeSetupKernel):

    def __init__(self, data, dist, partition_prior, num_adaptation_iters=float('inf'), use_prior_weight=False):
        SplitMergeSetupKernel.__init__(self, data, dist, partition_prior, num_adaptation_iters=num_adaptation_iters)

        self.use_prior_weight = use_prior_weight

        self.max_clusters_seen = 0

    def update(self, clustering):
        clustering = relabel_clustering(clustering)

        clusters = np.unique(clustering)

        num_clusters = len(np.unique(clustering))

        self.cluster_probs = np.zeros((num_clusters, num_clusters))

        self.clusters_to_data = {}

        self.data_to_clusters = {}

        margs = {}

        for c in clusters:
            cluster_data = self.data[clustering == c]

            cluster_params = self.dist.create_params_from_data(cluster_data)

            margs[c] = self.dist.log_marginal_likelihood(cluster_params)

            if self.use_prior_weight:
                margs[c] += self.partition_prior.log_tau_2(cluster_params.N)

            self.clusters_to_data[c] = np.where(clustering == c)[0].flatten()

            for i in self.clusters_to_data[c]:
                self.data_to_clusters[i] = c

        for c_i in clusters:
            log_p = np.ones(num_clusters) * float('-inf')

            for c_j in clusters:
                if c_i == c_j:
                    continue

                merged_data = self.data[(clustering == c_i) | (clustering == c_j)]

                merged_params = self.dist.create_params_from_data(merged_data)

                merge_marg = self.dist.log_marginal_likelihood(merged_params)

                if self.use_prior_weight:
                    merge_marg += self.partition_prior.log_tau_2(merged_params.N)

                log_p[c_j] = merge_marg - (margs[c_i] + margs[c_j])

            if num_clusters == 1:
                log_p[c_i] = 0

            else:
                log_p[c_i] = -np.log(num_clusters - 1) + log_sum_exp(log_p)

            self.cluster_probs[c_i], _ = exp_normalize(log_p)

    def _can_update(self, clustering):
        num_clusters = len(np.unique(clustering))

        if (num_clusters > self.max_clusters_seen) and (self.iter <= self.num_adaptation_iters):
            can_update = True

            self.max_clusters_seen = num_clusters

        else:
            can_update = False

        return can_update

    def _propose_anchors(self, num_anchors):
        if num_anchors != 2:
            raise Exception('ClusterInformedSplitMergeSetupKernel only works for 2 anchors')

        anchor_1 = np.random.randint(0, self.num_data_points)

        cluster_1 = self.data_to_clusters[anchor_1]

        cluster_2 = discrete_rvs(self.cluster_probs[cluster_1])

        cluster_members = set(self.clusters_to_data[cluster_2])

        cluster_members.discard(anchor_1)

        if len(cluster_members) == 0:
            anchor_1, anchor_2 = np.random.choice(np.arange(self.num_data_points), replace=False, size=2)

        else:
            anchor_2 = np.random.choice(list(cluster_members))

        return anchor_1, anchor_2


class PointInformedSplitMergeSetupKernel(SplitMergeSetupKernel):

    def __init__(self, data, dist, partition_prior, num_adaptation_iters=float('inf')):
        SplitMergeSetupKernel.__init__(self, data, dist, partition_prior, num_adaptation_iters=num_adaptation_iters)

        self.data_to_clusters = {}

        params = self.dist.create_params()

        self.log_seperate_margs = self.dist.log_predictive_likelihood_bulk(self.data, params)

    def update(self, clustering):
        pass

    def _can_update(self, clustering):
        return False

    def _propose_anchors(self, num_anchors):
        if num_anchors != 2:
            raise Exception('PointInformedSplitMergeSetupKernel only works for 2 anchors')

        anchor_1 = np.random.randint(0, self.num_data_points)

        if anchor_1 not in self.data_to_clusters:
            self._set_data_to_clusters(anchor_1)

        log_p_anchor = self.data_to_clusters[anchor_1].copy()

        u = np.random.random()

        alpha = np.random.beta(1, 9) * 100

        if u <= 0.5:
            x = np.percentile(log_p_anchor, alpha)

            log_p_anchor[log_p_anchor > x] = float('-inf')

            log_p_anchor[log_p_anchor <= x] = 0

        else:
            x = np.percentile(log_p_anchor, 100 - alpha)

            log_p_anchor[log_p_anchor > x] = 0

            log_p_anchor[log_p_anchor <= x] = float('-inf')

        log_p_anchor[anchor_1] = float('-inf')

        if np.isneginf(np.max(log_p_anchor)):
            idx = np.arange(self.num_data_points)

            idx = list(idx)

            idx.remove(anchor_1)

            anchor_2 = np.random.choice(idx)

        else:
            idx = np.where(~np.isneginf(log_p_anchor))[0].flatten()

            anchor_2 = np.random.choice(idx)

        return anchor_1, anchor_2

    def _set_data_to_clusters(self, i):
        self.data_to_clusters[i] = np.zeros(self.num_data_points)

        params = self.dist.create_params_from_data(self.data[i])

        log_pairwise_margs = self.dist.log_predictive_likelihood_bulk(self.data, params)

        for j in range(self.num_data_points):
            self.data_to_clusters[i][j] = log_pairwise_margs[j] - \
                (self.log_seperate_margs[i] + self.log_seperate_margs[j])
