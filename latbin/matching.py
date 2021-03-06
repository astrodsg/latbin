from copy import copy

import numpy as np
import scipy.sparse
import pandas as pd
from latbin.lattice import *

def brute_match(data1, data2, tolerance=0):
    """a brute force matching function.
    Uses a slow N^2 double for loop algorithm.
    may be faster than using the match algorithm for situations where
    either the number of matches is a significant fraction of N^2 or
    the number of dimensions is comparable to the number of data points
    or for very small matching problems.
    """
    idxs_1, idxs_2, distances = [], [], []
    for i in range(len(data1)):
        for j in range(len(data2)):
            dist = np.sum((data1[i]-data2[j])**2) 
            if dist <= tolerance**2:
                idxs_1.append(i)
                idxs_2.append(j)
                distances.append(np.sqrt(dist))
    return idxs_1, idxs_2, distances


class MatchingIndexer(object):
    """Class for storing pre-calculated neighborhood dictionaries to make matching against the same data set many times quick.
    """
    
    def __init__(self, x, tolerance):
        self.x = x
        self.tolerance=tolerance
        
        npts, ndim = self.x.shape        
        
        #generate the matching lattice cells
        self.lat = ALattice(ndim, scale=self.tolerance*1.3)
        self.neighborhood_vecs = self.lat.neighborhood(
            lattice_space_radius=2.0, include_origin=True)
        
        xquant = self.lat.quantize(x)
        self.matching_dict = {}
        for shift_idx in range(len(self.neighborhood_vecs)):
            shift_vec = self.neighborhood_vecs[shift_idx]
            for xq_idx in range(npts):
                xtup = tuple(xquant[xq_idx] + shift_vec) 
                match_list = self.matching_dict.get(xtup, [])
                match_list.append(xq_idx)
                self.matching_dict[xtup] = match_list
    
    
    def match(self, x, cleanup=True):
        n_out = len(x)
        potential_matches = []
        xquant = self.lat.quantize(x)
        for out_idx in range(n_out):
            xtup = tuple(xquant[out_idx])
            cp_matches = self.matching_dict.get(xtup, [])
            for midx in cp_matches:
                match_tup = (out_idx, midx)
                potential_matches.append(match_tup)
        tol_sq = self.tolerance**2
        cleaned_matches = []
        distances = []
        for idx1, idx2 in potential_matches:
            dist_sq = np.sum((x[idx1] - self.x[idx2])**2)
            if dist_sq < tol_sq:
                cleaned_matches.append((idx1, idx2))
                distances.append(dist_sq)
        distances = np.sqrt(np.asarray(distances))
        return cleaned_matches, distances
    
    
    def distance_matrix(self, x):
        idxs, distances = self.match(x, cleanup=True)
        idxs = np.asarray(idxs)
        mat_shape = (len(x), len(self.x))
        coomat = scipy.sparse.coo_matrix(
            (distances, idxs.transpose()), 
            shape=mat_shape
        )
        return coomat


def match(data1, data2, tolerance=0, cols=None):
    """efficiently find all matching rows between two data sets
    
    data1: numpy.ndarray or pandas.DataFrame
      data set to be matched
    data2: numpy.ndarray or pandas.DataFrame
      data set to be matched
    tolerance: float
      maximum distance between rows to be considered a match.
    cols: list
      the indexes of the columns to be used in the matching.
      if None the columns of data1 are assumed
      e.g. to match between data sets using the first and third columns in
      each data set we would use, 
      cols = [0, 2]
      If the columns we wish to match have different indexes in the different
      data sets we can specify a tuple instead of a single index.
      e.g. in order to match the first column in the first data set with the 
      5th column in the second data set and the 4th column in both data sets
      we could use,
      cols = [(0, 4), 3]
    """
    if not isinstance(data1, pd.DataFrame):
        data1 = pd.DataFrame(np.asarray(data1))
    if not isinstance(data2, pd.DataFrame):
        data2 = pd.DataFrame(np.asarray(data2))
    if cols == None:
        cols = data1.columns
    nmatch_cols = len(cols)
    cols1 = []
    cols2 = []
    for col_idx in range(len(cols)):
        ccol = cols[col_idx]
        if isinstance(ccol, tuple):
            c1, c2 = ccol
            cols1.append(c1)
            cols2.append(c2)
        cols1.append(ccol)
        cols2.append(ccol)
    #quantize
    if tolerance <= 0:
        raise NotImplementedError()
    
    qlat = ALattice(nmatch_cols, scale=1.3*tolerance)
    
    switched = False
    if len(data2) > len(data1):
        switched = True
        temp = data1
        data1 = data2
        data2 = temp
    
    d1vals = data1[cols1].values
    d2vals = data2[cols2].values
    long_pts = qlat.quantize(d1vals)
    short_pts = qlat.quantize(d2vals)
    
    all_trans = [short_pts]
    neighbor_vecs = qlat.neighborhood(lattice_space_radius=2.1, include_origin=False)
    
    for neighbor_vec in neighbor_vecs:
        all_trans.append(short_pts + neighbor_vec)
    
    #make the shifted points into dictionaries
    cdict = {}
    for atrans in all_trans:
        for pvec_idx in range(len(atrans)):
            pvec = atrans[pvec_idx]
            ptup = tuple(pvec)
            dval = cdict.get(ptup)
            if dval is None:
                dval = set()
            dval.add(pvec_idx)
            cdict[ptup] = dval
    
    idxs_1 = []
    idxs_2 = []
    distances = []
    dthresh = tolerance**2
    for long_idx in range(len(long_pts)):
        ltup = tuple(long_pts[long_idx])
        possible_match_set = cdict.get(ltup)
        if not possible_match_set is None:
            #calculate actual distance
            for match_idx in possible_match_set:
                dist = np.sum((d1vals[long_idx] - d2vals[match_idx])**2)
                if dist <= dthresh:
                    idxs_1.append(long_idx)
                    idxs_2.append(match_idx)
                    distances.append(np.sqrt(dist))
    
    if switched:
        temp = idxs_1
        idxs_1 = idxs_2
        idxs_2 = temp
    
    idxs_1 = np.asarray(idxs_1)
    idxs_2 = np.asarray(idxs_2)
    distances = np.asarray(distances)
    
    return idxs_1, idxs_2, distances


def sparse_distance_matrix(data1, data2=None, max_dist=1.0, rbf=None, cols=None,):
    """matches the rows of input data against themselves and generates a
    sparse n_rows by n_rows matrix with entries at i, j if and only if 
    np.sum((data[i]-data[j])**2) < max_dist**2 
    the entries are determined by the rbf function provided. 
    
    
    parameters
    ----------
    data: numpy.ndarray or pandas.DataFrame
      the data array (n_points, n_dimensions). 
    data2: numpy.ndarray or pandas.DataFrame
      an optional second data array to match against and measure distance to.
      if not specified then the rows in data are matched against themselves.
    max_dist: float
      pairs of points with distances greater than this will have zero entries
      in the resulting sparse matrix
    rbf: function
      a function to take a vector of distances to a vector of matrix entries.
      defaults to exp(-distance**2)
    cols: see latbin.matching.match documentation for more info 
    """
    if data2 is None:
        data2 = data1
    if rbf is None:
        rbf = lambda x: np.exp(-0.5*x**2)
    idxs_1, idxs_2, distances = match(data1, data2, tolerance=max_dist, cols=cols)
    entries = rbf(distances)
    n1 = len(data1)
    n2 = len(data2)
    coomat = scipy.sparse.coo_matrix((entries, (idxs_1, idxs_2)), shape=(n1, n2))
    return coomat
    
